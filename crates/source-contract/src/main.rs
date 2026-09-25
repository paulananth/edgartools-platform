//! Parse one bronze artifact with a Source Contract directory.
//!
//! The 13F contract names `blank_missing_token@1`. That step is registered
//! here; the engine does not know the source.

use std::env;
use std::fs;
use std::path::PathBuf;
use std::process::ExitCode;

use source_contract::{blank_missing_token, Engine};

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
    let engine = match Engine::load(PathBuf::from(&contract).as_path()) {
        Ok(engine) => engine.with_step("blank_missing_token@1", blank_missing_token),
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
    match engine.parse(&bytes) {
        Ok(tables) => {
            for (name, rows) in tables {
                println!("{name}\t{}", rows.len());
            }
            ExitCode::SUCCESS
        }
        Err(err) => {
            eprintln!("parse: {err}");
            ExitCode::from(1)
        }
    }
}
