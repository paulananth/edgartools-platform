//! Bounded delimited text, CSV or TSV, read as a stream: a header line, then one
//! record per line, each handed on as a JSON object of header to text, so the
//! ordinary configured projection reads it. Whole files are read the same way by
//! `formats::csv` and `formats::tsv`; a large one is read here, one record at a
//! time. Callbacks prepare candidates. Only a successful EOF permits publication.
use std::cell::Cell;
use std::io::{self, Read};

use serde_json::{Map, Value};

use crate::{json_sequence::Stats, Rejected};

#[derive(Clone, Copy)]
pub struct Limits {
    pub max_bytes: usize,
    /// One record's bytes as written, separators included.
    pub max_record: usize,
    pub max_records: usize,
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Format {
    /// Commas, with CSV quoting.
    Csv,
    /// Tabs, with no quoting: a tab never occurs inside a value.
    Tsv,
}

impl Format {
    pub fn named(name: &str) -> Result<Self, Rejected> {
        match name {
            "csv" => Ok(Self::Csv),
            "tsv" => Ok(Self::Tsv),
            other => Err(Rejected::new("contract", format!("a delimited stream is csv or tsv, not {other}"))),
        }
    }
}

struct Budget<'a, R> {
    source: R,
    total: &'a Cell<usize>,
    exceeded: &'a Cell<bool>,
    max_bytes: usize,
}

impl<R: Read> Read for Budget<'_, R> {
    fn read(&mut self, target: &mut [u8]) -> io::Result<usize> {
        let n = self.source.read(target)?;
        match self.total.get().checked_add(n) {
            Some(total) if total <= self.max_bytes => {
                self.total.set(total);
                Ok(n)
            }
            _ => {
                self.exceeded.set(true);
                Err(io::Error::new(io::ErrorKind::InvalidData, "delimited byte budget exceeded"))
            }
        }
    }
}

fn text(bytes: &[u8], encoding: &str) -> Result<String, Rejected> {
    let decoded = crate::formats::decode_one(bytes, encoding)?;
    String::from_utf8(decoded.into_owned()).map_err(|error| Rejected::new("malformed", error))
}

/// Reads every record, handing each to `consume` with its zero-based ordinal.
/// `encoding` is one declared encoding: deciding between two needs the whole file.
pub fn scan<R: Read, F: FnMut(Value, usize) -> Result<(), Rejected>>(
    source: R, format: Format, encoding: &str, limits: Limits, mut consume: F,
) -> Result<Stats, Rejected> {
    if limits.max_bytes == 0 || limits.max_record == 0 || !crate::formats::ENCODINGS.contains(&encoding) {
        return Err(Rejected::new("contract", "invalid delimited stream encoding or limits"));
    }
    let total = Cell::new(0);
    let exceeded = Cell::new(false);
    let budget = Budget { source, total: &total, exceeded: &exceeded, max_bytes: limits.max_bytes };
    let mut reader = ::csv::ReaderBuilder::new()
        .has_headers(true)
        .delimiter(if format == Format::Tsv { b'\t' } else { b',' })
        .quoting(format == Format::Csv)
        .from_reader(budget);
    let failed = |error: ::csv::Error| {
        if exceeded.get() {
            Rejected::new("limit_exceeded", format!("more than {} bytes", limits.max_bytes))
        } else {
            Rejected::new("malformed", error)
        }
    };
    let headers = reader.byte_headers().map_err(failed)?.clone();
    let names = headers.iter().map(|name| text(name, encoding)).collect::<Result<Vec<_>, _>>()?;
    let mut record = ::csv::ByteRecord::new();
    let mut count = 0usize;
    while reader.read_byte_record(&mut record).map_err(failed)? {
        if count == limits.max_records {
            return Err(Rejected::new("limit_exceeded", format!("more than {} records", limits.max_records)));
        }
        if record.as_slice().len() + record.len() > limits.max_record {
            return Err(Rejected::new("limit_exceeded", format!("record {} is over {} bytes", count + 1, limits.max_record)));
        }
        let mut object = Map::with_capacity(names.len());
        for (name, cell) in names.iter().zip(record.iter()) {
            object.insert(name.clone(), Value::String(text(cell, encoding)?));
        }
        consume(Value::Object(object), count)?;
        count += 1;
    }
    Ok(Stats { records: count, bytes: total.get() })
}
