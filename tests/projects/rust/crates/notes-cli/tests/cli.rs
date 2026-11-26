//! The command driven as a person would run it.

use std::path::PathBuf;
use std::process::{Command, Output};

fn file(name: &str) -> PathBuf {
    let path = std::env::temp_dir().join(format!("notes-cli-{}-{name}", std::process::id()));
    let _ = std::fs::remove_file(&path);
    path
}

fn run(path: &PathBuf, args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_notes-cli"))
        .arg(path)
        .args(args)
        .output()
        .expect("the command runs")
}

#[test]
fn notes_added_and_finished_are_listed_from_the_file() {
    let path = file("list");
    assert_eq!(
        run(&path, &["add", "write the report"]).stdout,
        b"added 1\n"
    );
    assert_eq!(run(&path, &["add", "send it"]).stdout, b"added 2\n");
    assert_eq!(run(&path, &["done", "1"]).stdout, b"done 1\n");
    let listed = run(&path, &["list"]);
    assert!(listed.status.success());
    assert_eq!(listed.stdout, b"[x] write the report\n[ ] send it\n");
    std::fs::remove_file(&path).unwrap();
}

#[test]
fn a_mistake_exits_2_and_says_what_is_wrong() {
    let path = file("mistake");
    let unknown = run(&path, &["done", "4"]);
    assert_eq!(unknown.status.code(), Some(2));
    assert_eq!(unknown.stderr, b"there is no note 4\n");
    let usage = run(&path, &["remove"]);
    assert_eq!(usage.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&usage.stderr).starts_with("usage: "));
}
