//! notes-cli FILE add TITLE | done NUMBER | list

use std::env;
use std::error::Error;
use std::path::Path;
use std::process::ExitCode;

use notes::Notes;

const USAGE: &str = "usage: notes-cli FILE add TITLE | done NUMBER | list";

fn run(args: &[String]) -> Result<String, Box<dyn Error>> {
    let words: Vec<&str> = args.iter().map(String::as_str).collect();
    let (path, command) = match words.split_first() {
        Some((path, command)) => (Path::new(path), command),
        None => return Err(USAGE.into()),
    };
    let mut notes = Notes::load(path)?;
    match command {
        ["add", title] => {
            let number = notes.add(title)?;
            notes.save(path)?;
            Ok(format!("added {number}\n"))
        }
        ["done", number] => {
            notes.finish(number.parse()?)?;
            notes.save(path)?;
            Ok(format!("done {number}\n"))
        }
        ["list"] => Ok(notes.render()),
        _ => Err(USAGE.into()),
    }
}

fn main() -> ExitCode {
    let args: Vec<String> = env::args().skip(1).collect();
    match run(&args) {
        Ok(output) => {
            print!("{output}");
            ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("{error}");
            ExitCode::from(2)
        }
    }
}
