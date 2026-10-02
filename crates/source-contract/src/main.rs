//! Parse one bronze artifact with a Source Contract directory.
//!
//! The 13F contract names `blank_missing_token@1`. That step is registered
//! here; the engine does not know the source.

use std::env;
use std::fs;
use std::path::PathBuf;
use std::process::ExitCode;

use source_contract::{blank_missing_token, Engine, Lookups, Step, Steps};

fn main() -> ExitCode {
    let mut args = env::args().skip(1);
    let Some(contract) = args.next() else {
        eprintln!("usage: source-contract <contract.yaml> <artifact>");
        return ExitCode::from(2);
    };
    let Some(artifact) = args.next() else {
        eprintln!("usage: source-contract <contract.yaml> <artifact>");
        return ExitCode::from(2);
    };
    let mut steps = Steps::new();
    steps.insert("blank_missing_token@1".into(), Box::new(blank_missing_token) as Step);
    let engine = match Engine::load(PathBuf::from(&contract).as_path(), steps) {
        Ok(engine) => engine,
        Err(err) => {
            eprintln!("contract: {err}");
            return ExitCode::from(1);
        }
    };
    let bytes = match fs::read(&artifact) {
        Ok(bytes) => bytes,
        Err(err) => {
            eprintln!("artifact: {err}");
            return ExitCode::from(1);
        }
    };
    match engine.read(&bytes, &Lookups::new()) {
        Ok(reading) => {
            for (name, rows) in reading.tables {
                println!("{name}\t{}", rows.len());
            }
            println!("deferred\t{}", reading.deferred.len());
            ExitCode::SUCCESS
        }
        Err(err) => {
            eprintln!("parse: {err}");
            ExitCode::from(1)
        }
    }
}
