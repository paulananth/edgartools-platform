//! Time a streaming 13F information-table parse. Same pin and cache as the
//! Python comparison. File reads are outside the clock, matching that script.

use std::fs;
use std::path::PathBuf;
use std::time::Instant;

use quick_xml::events::Event;
use quick_xml::Reader;
use serde_json::Value;

fn local_name(qname: &[u8]) -> &[u8] {
    match qname.iter().rposition(|b| *b == b':') {
        Some(i) => &qname[i + 1..],
        None => qname,
    }
}

fn blank(text: &str) -> Option<&str> {
    let text = text.trim();
    if text.is_empty() || text.eq_ignore_ascii_case("none") || text.eq_ignore_ascii_case("nan") {
        None
    } else {
        Some(text)
    }
}

struct Fold {
    rows: u64,
    value_sum: f64,
    share_sum: f64,
    hash: u64,
}

fn mix(hash: u64, bytes: &[u8]) -> u64 {
    let mut hash = hash;
    for byte in bytes {
        hash = hash.wrapping_mul(16777619).wrapping_add(*byte as u64);
    }
    hash
}

fn parse_file(bytes: &[u8], fold: &mut Fold) -> Result<(), Box<dyn std::error::Error>> {
    let mut reader = Reader::from_reader(bytes);
    reader.config_mut().trim_text(true);
    let mut buf = Vec::new();
    let mut capture: Option<String> = None;
    let mut in_row = false;
    let mut depth = 0usize;
    let mut issuer = String::new();
    let mut title = String::new();
    let mut cusip = String::new();
    let mut put_call = String::new();
    let mut discretion = String::new();
    let mut share_type = String::new();
    let mut value = String::new();
    let mut shares = String::new();
    let mut sole = String::new();
    let mut shared = String::new();
    let mut none = String::new();

    loop {
        match reader.read_event_into(&mut buf) {
            Ok(Event::Start(event)) => {
                depth += 1;
                let raw = event.name().as_ref().to_vec();
                let name = local_name(&raw).to_vec();
                if name == b"infoTable" {
                    in_row = true;
                    issuer.clear();
                    title.clear();
                    cusip.clear();
                    put_call.clear();
                    discretion.clear();
                    share_type.clear();
                    value.clear();
                    shares.clear();
                    sole.clear();
                    shared.clear();
                    none.clear();
                }
                capture = std::str::from_utf8(&name).ok().map(str::to_string);
            }
            Ok(Event::Text(event)) => {
                if !in_row {
                    buf.clear();
                    continue;
                }
                let text = event.unescape()?;
                match capture.as_deref() {
                    Some("nameOfIssuer") => issuer.push_str(&text),
                    Some("titleOfClass") => title.push_str(&text),
                    Some("cusip") => cusip.push_str(&text),
                    Some("putCall") => put_call.push_str(&text),
                    Some("investmentDiscretion") => discretion.push_str(&text),
                    Some("sshPrnamtType") => share_type.push_str(&text),
                    Some("value") => value.push_str(&text),
                    Some("sshPrnamt") => shares.push_str(&text),
                    Some("Sole") => sole.push_str(&text),
                    Some("Shared") => shared.push_str(&text),
                    Some("None") => none.push_str(&text),
                    _ => {}
                }
            }
            Ok(Event::End(event)) => {
                depth = depth.checked_sub(1).ok_or("unexpected closing element")?;
                let raw = event.name().as_ref().to_vec();
                let name = local_name(&raw).to_vec();
                if name == b"infoTable" {
                    fold.rows += 1;
                    fold.value_sum += value.trim().parse::<f64>().unwrap_or(0.0);
                    fold.share_sum += shares.trim().parse::<f64>().unwrap_or(0.0);
                    for field in [&issuer, &title, &cusip, &put_call, &discretion, &share_type] {
                        if let Some(text) = blank(field) {
                            fold.hash = mix(fold.hash, text.as_bytes());
                        }
                    }
                    in_row = false;
                }
                capture = None;
            }
            Ok(Event::Eof) => break,
            Err(error) => return Err(error.into()),
            _ => {}
        }
        buf.clear();
    }
    if depth != 0 || in_row {
        return Err("truncated XML".into());
    }
    Ok(())
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // LIMIT [PIN [CACHE]]; defaults stay local and bounded.
    let mut args = std::env::args().skip(1);
    let limit: usize = args.next().unwrap_or_else(|| "10".into()).parse()?;
    let default_pin = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../docs/research/heavy-parse-s3-pin-13f-2026-09-25.json");
    let pin_path = args.next().map(PathBuf::from).unwrap_or(default_pin);
    let cache = match args.next() {
        Some(path) => PathBuf::from(path),
        None => {
            PathBuf::from(std::env::var("HOME")?).join(".local/share/edgartools/heavy-parse-13f")
        }
    };
    if args.next().is_some() {
        return Err("usage: thirteenf-bench LIMIT [PIN [CACHE]]".into());
    }
    let pin: Value = serde_json::from_str(&fs::read_to_string(pin_path)?)?;
    let rows = pin["sample_1000"]
        .as_array()
        .ok_or("pin has no sample_1000")?;
    if limit == 0 || limit > rows.len() {
        return Err("limit must be positive and no greater than the pinned sample".into());
    }
    let mut fold = Fold {
        rows: 0,
        value_sum: 0.0,
        share_sum: 0.0,
        hash: 0,
    };
    let mut parse_ns = 0u128;
    let mut read_ns = 0u128;
    for item in rows.iter().take(limit) {
        let etag = item["etag"].as_str().ok_or("pin has no ETag")?;
        let started = Instant::now();
        let bytes = fs::read(cache.join(etag))?;
        read_ns += started.elapsed().as_nanos();
        if item["size"].as_u64() != Some(bytes.len() as u64) {
            return Err("cached size differs from pin".into());
        }
        let started = Instant::now();
        parse_file(&bytes, &mut fold)?;
        parse_ns += started.elapsed().as_nanos();
    }
    println!(
        "files={limit} rows={} value_sum={:.0} share_sum={:.0} hash={} parse_seconds={:.3} read_seconds={:.3}",
        fold.rows,
        fold.value_sum,
        fold.share_sum,
        fold.hash,
        parse_ns as f64 / 1e9,
        read_ns as f64 / 1e9,
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fold() -> Fold {
        Fold {
            rows: 0,
            value_sum: 0.0,
            share_sum: 0.0,
            hash: 0,
        }
    }

    #[test]
    fn namespace_and_entity_text() {
        let mut result = fold();
        parse_file(br#"<n:informationTable xmlns:n="urn:test"><n:infoTable><n:nameOfIssuer>A &amp; B</n:nameOfIssuer><n:value>12</n:value><n:sshPrnamt>3</n:sshPrnamt></n:infoTable></n:informationTable>"#, &mut result).unwrap();
        assert_eq!(result.rows, 1);
        assert_eq!(result.value_sum, 12.0);
        assert_eq!(result.share_sum, 3.0);
        assert_eq!(result.hash, mix(0, b"A & B"));
    }

    #[test]
    fn malformed_xml_is_an_error() {
        assert!(parse_file(b"<informationTable><infoTable></wrong>", &mut fold()).is_err());
        assert!(parse_file(b"<informationTable><infoTable></infoTable>", &mut fold()).is_err());
    }

    #[test]
    fn missing_tokens_are_blank() {
        assert_eq!(blank(" None "), None);
        assert_eq!(blank("nan"), None);
        assert_eq!(blank("A"), Some("A"));
    }
}
