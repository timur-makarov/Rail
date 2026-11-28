use notes::{Error, Notes};

#[test]
fn what_is_rendered_parses_back_to_the_same_notes() {
    let mut notes = Notes::default();
    notes.add("write the report").unwrap();
    notes.add("send [it]").unwrap();
    notes.finish(2).unwrap();
    assert_eq!(Notes::parse(&notes.render()), Ok(notes));
}

#[test]
fn a_line_that_is_not_a_note_is_named() {
    assert_eq!(Notes::parse("[ ] one\nsend it\n"), Err(Error::BadLine(2)));
}

#[test]
fn a_file_that_is_not_there_holds_no_notes() {
    let path = std::env::temp_dir().join(format!("notes-missing-{}", std::process::id()));
    assert!(Notes::load(&path).unwrap().all().is_empty());
}
