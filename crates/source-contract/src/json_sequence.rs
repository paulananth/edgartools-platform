//! Bounded single-wrapper JSON arrays. Consumers prepare candidates; EOF
//! verification must succeed before a caller publishes or commits anything.
use std::cell::Cell;
use std::fmt;
use std::io::{self, BufReader, Read};

use serde::de::{self, DeserializeSeed, MapAccess, SeqAccess, Visitor};
use serde_json::{Map, Number, Value};

use crate::Rejected;

const BUFFER: usize = 65536;

#[derive(Clone, Copy)]
pub struct Limits {
    pub max_bytes: usize,
    /// Encoded record bytes. Raw records permit BUFFER bytes of whitespace
    /// and buffering headroom, matching the historical bounded archive reader.
    pub max_record: usize,
    pub max_records: usize,
    pub max_depth: usize,
    pub min_integer: i64,
}

#[derive(Debug, PartialEq)]
pub struct Stats {
    pub records: usize,
    pub bytes: usize,
}

struct Budget<'a, R> {
    reader: R,
    total: &'a Cell<usize>,
    since_record: &'a Cell<usize>,
    failed: &'a Cell<bool>,
    limits: Limits,
}

impl<R: Read> Read for Budget<'_, R> {
    fn read(&mut self, buffer: &mut [u8]) -> io::Result<usize> {
        if self.failed.get() { return Err(io::Error::new(io::ErrorKind::InvalidData, "JSON stream byte budget exceeded")); }
        let size = buffer.len().min(BUFFER);
        let count = self.reader.read(&mut buffer[..size])?;
        let total = self.total.get().checked_add(count);
        let since = self.since_record.get().checked_add(count);
        if total.is_none_or(|n| n > self.limits.max_bytes)
            || since.is_none_or(|n| n > self.limits.max_record.saturating_add(BUFFER)) {
            self.failed.set(true);
            return Err(io::Error::new(io::ErrorKind::InvalidData, "JSON stream byte budget exceeded"));
        }
        self.total.set(total.unwrap());
        self.since_record.set(since.unwrap());
        Ok(count)
    }
}

struct JsonValue {
    depth: usize,
    maximum: usize,
}

impl<'de> DeserializeSeed<'de> for JsonValue {
    type Value = Value;
    fn deserialize<D: de::Deserializer<'de>>(self, deserializer: D) -> Result<Value, D::Error> {
        if self.depth > self.maximum { return Err(de::Error::custom("JSON nesting exceeds bound")); }
        deserializer.deserialize_any(self)
    }
}

impl<'de> Visitor<'de> for JsonValue {
    type Value = Value;
    fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result { formatter.write_str("a bounded JSON value") }
    fn visit_unit<E: de::Error>(self) -> Result<Value, E> { Ok(Value::Null) }
    fn visit_bool<E: de::Error>(self, value: bool) -> Result<Value, E> { Ok(Value::Bool(value)) }
    fn visit_i64<E: de::Error>(self, value: i64) -> Result<Value, E> { Ok(Value::Number(value.into())) }
    fn visit_u64<E: de::Error>(self, value: u64) -> Result<Value, E> {
        let value = i64::try_from(value).map_err(|_| E::custom("JSON integer exceeds signed 64-bit bound"))?;
        Ok(Value::Number(value.into()))
    }
    fn visit_f64<E: de::Error>(self, value: f64) -> Result<Value, E> {
        Number::from_f64(value).map(Value::Number).ok_or_else(|| E::custom("nonfinite JSON number"))
    }
    fn visit_str<E: de::Error>(self, value: &str) -> Result<Value, E> { Ok(Value::String(value.into())) }
    fn visit_string<E: de::Error>(self, value: String) -> Result<Value, E> { Ok(Value::String(value)) }
    fn visit_seq<A: SeqAccess<'de>>(self, mut sequence: A) -> Result<Value, A::Error> {
        let mut values = Vec::new();
        while let Some(value) = sequence.next_element_seed(JsonValue { depth: self.depth + 1, maximum: self.maximum })? {
            values.push(value);
        }
        Ok(Value::Array(values))
    }
    fn visit_map<A: MapAccess<'de>>(self, mut object: A) -> Result<Value, A::Error> {
        let mut values = Map::new();
        while let Some(key) = object.next_key::<String>()? {
            if values.contains_key(&key) { return Err(de::Error::custom("duplicate JSON key")); }
            let value = object.next_value_seed(JsonValue { depth: self.depth + 1, maximum: self.maximum })?;
            values.insert(key, value);
        }
        Ok(Value::Object(values))
    }
}

struct Records<'a, F> {
    limits: Limits,
    since_record: &'a Cell<usize>,
    count: &'a mut usize,
    consume: &'a mut F,
    consumer_error: &'a mut Option<Rejected>,
}

impl<'de, F: FnMut(Value, usize) -> Result<(), Rejected>> DeserializeSeed<'de> for Records<'_, F> {
    type Value = ();
    fn deserialize<D: de::Deserializer<'de>>(self, deserializer: D) -> Result<(), D::Error> {
        deserializer.deserialize_seq(self)
    }
}

impl<'de, F: FnMut(Value, usize) -> Result<(), Rejected>> Visitor<'de> for Records<'_, F> {
    type Value = ();
    fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result { formatter.write_str("an array of JSON objects") }
    fn visit_seq<A: SeqAccess<'de>>(self, mut sequence: A) -> Result<(), A::Error> {
        loop {
            let Some(raw) = sequence.next_element::<Box<serde_json::value::RawValue>>()? else { return Ok(()) };
            if raw.get().len() > self.limits.max_record.saturating_add(BUFFER) {
                return Err(de::Error::custom("JSON record exceeds raw buffering bound"));
            }
            check_integers(raw.get(), self.limits.min_integer).map_err(de::Error::custom)?;
            let mut parser = serde_json::Deserializer::from_str(raw.get());
            let record = JsonValue { depth: 0, maximum: self.limits.max_depth }.deserialize(&mut parser).map_err(de::Error::custom)?;
            if !record.is_object() { return Err(de::Error::custom("JSON record must be an object")); }
            if *self.count >= self.limits.max_records { return Err(de::Error::custom("JSON record count exceeds bound")); }
            if serde_json::to_vec(&record).map_err(de::Error::custom)?.len() > self.limits.max_record {
                return Err(de::Error::custom("JSON record exceeds encoded byte bound"));
            }
            self.since_record.set(0);
            if let Err(error) = (self.consume)(record, *self.count) {
                *self.consumer_error = Some(error);
                return Err(de::Error::custom("record consumer refused"));
            }
            *self.count += 1;
        }
    }
}

// RawValue has already validated JSON syntax. Check integer lexemes before
// serde's fallback to floating point can change an out-of-range integer.
fn check_integers(raw: &str, minimum: i64) -> Result<(), &'static str> {
    let bytes = raw.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'"' {
            i += 1;
            while i < bytes.len() {
                if bytes[i] == b'\\' { i += 2; }
                else if bytes[i] == b'"' { i += 1; break; }
                else { i += 1; }
            }
        } else if bytes[i] == b'-' || bytes[i].is_ascii_digit() {
            let start = i;
            while i < bytes.len() && matches!(bytes[i], b'-' | b'+' | b'.' | b'e' | b'E' | b'0'..=b'9') { i += 1; }
            let number = &raw[start..i];
            if !number.contains(['.', 'e', 'E']) && number.parse::<i64>().map_or(true, |n| n < minimum) {
                return Err("JSON integer exceeds signed 64-bit bound");
            }
        } else { i += 1; }
    }
    Ok(())
}

struct Envelope<'a, F> {
    wrapper: &'a str,
    records: Records<'a, F>,
}

impl<'de, F: FnMut(Value, usize) -> Result<(), Rejected>> DeserializeSeed<'de> for Envelope<'_, F> {
    type Value = ();
    fn deserialize<D: de::Deserializer<'de>>(self, deserializer: D) -> Result<(), D::Error> {
        deserializer.deserialize_map(self)
    }
}

impl<'de, F: FnMut(Value, usize) -> Result<(), Rejected>> Visitor<'de> for Envelope<'_, F> {
    type Value = ();
    fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result { formatter.write_str("one named JSON array") }
    fn visit_map<A: MapAccess<'de>>(self, mut object: A) -> Result<(), A::Error> {
        if object.next_key::<String>()?.as_deref() != Some(self.wrapper) {
            return Err(de::Error::custom("JSON wrapper differs"));
        }
        object.next_value_seed(self.records)?;
        if object.next_key::<String>()?.is_some() { return Err(de::Error::custom("additional JSON wrapper key")); }
        Ok(())
    }
}

pub fn scan<R: Read, F: FnMut(Value, usize) -> Result<(), Rejected>>(
    reader: R, wrapper: &str, limits: Limits, mut consume: F,
) -> Result<Stats, Rejected> {
    if wrapper.is_empty() || wrapper.len() > 128 || limits.max_bytes == 0 || limits.max_record == 0
        || !(1..=64).contains(&limits.max_depth) {
        return Err(Rejected::new("contract", "invalid JSON stream wrapper or limits"));
    }
    let total = Cell::new(0);
    let since_record = Cell::new(0);
    let failed = Cell::new(false);
    let budget = Budget { reader, total: &total, since_record: &since_record, failed: &failed, limits };
    let mut parser = serde_json::Deserializer::from_reader(BufReader::with_capacity(BUFFER, budget));
    let mut count = 0;
    let mut consumer_error = None;
    let result = Envelope { wrapper, records: Records { limits, since_record: &since_record,
        count: &mut count, consume: &mut consume, consumer_error: &mut consumer_error } }.deserialize(&mut parser)
        .and_then(|_| parser.end());
    if let Some(error) = consumer_error { return Err(error); }
    result.map_err(|error| Rejected::new(if failed.get() { "limit_exceeded" } else { "malformed" }, error))?;
    Ok(Stats { records: count, bytes: total.get() })
}
