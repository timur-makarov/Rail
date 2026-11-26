//! Notes kept in a text file, one per line: `[ ] title` or `[x] title`.

use std::fmt;
use std::fs;
use std::io;
use std::path::Path;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Note {
    pub title: String,
    pub done: bool,
}

#[derive(Debug, PartialEq, Eq)]
pub enum Error {
    NoTitle,
    NoSuchNote(usize),
    BadLine(usize),
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::NoTitle => write!(f, "a note needs a title"),
            Error::NoSuchNote(number) => write!(f, "there is no note {number}"),
            Error::BadLine(line) => write!(f, "line {line} is not a note"),
        }
    }
}

impl std::error::Error for Error {}

#[derive(Debug, Default, PartialEq, Eq)]
pub struct Notes {
    items: Vec<Note>,
}

impl Notes {
    pub fn add(&mut self, title: &str) -> Result<usize, Error> {
        if title.is_empty() {
            return Err(Error::NoTitle);
        }
        self.items.push(Note {
            title: title.to_string(),
            done: false,
        });
        Ok(self.items.len())
    }

    /// Marks note `number` done; notes are numbered from 1, in the order they were added.
    pub fn finish(&mut self, number: usize) -> Result<(), Error> {
        match number.checked_sub(1).and_then(|at| self.items.get_mut(at)) {
            Some(note) => {
                note.done = true;
                Ok(())
            }
            None => Err(Error::NoSuchNote(number)),
        }
    }

    pub fn all(&self) -> &[Note] {
        &self.items
    }

    pub fn parse(text: &str) -> Result<Notes, Error> {
        let mut items = Vec::new();
        for (at, line) in text.lines().enumerate() {
            let (done, title) = match (line.strip_prefix("[ ] "), line.strip_prefix("[x] ")) {
                (Some(title), _) => (false, title),
                (_, Some(title)) => (true, title),
                _ => return Err(Error::BadLine(at + 1)),
            };
            items.push(Note {
                title: title.to_string(),
                done,
            });
        }
        Ok(Notes { items })
    }

    pub fn render(&self) -> String {
        self.items
            .iter()
            .map(|note| format!("[{}] {}\n", if note.done { 'x' } else { ' ' }, note.title))
            .collect()
    }

    /// The notes in the file; a file that isn't there yet holds none.
    pub fn load(path: &Path) -> Result<Notes, Box<dyn std::error::Error>> {
        match fs::read_to_string(path) {
            Ok(text) => Ok(Notes::parse(&text)?),
            Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(Notes::default()),
            Err(error) => Err(error.into()),
        }
    }

    pub fn save(&self, path: &Path) -> io::Result<()> {
        fs::write(path, self.render())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn notes_are_numbered_in_the_order_they_were_added() {
        let mut notes = Notes::default();
        assert_eq!(notes.add("write the report"), Ok(1));
        assert_eq!(notes.add("send it"), Ok(2));
        assert_eq!(notes.add(""), Err(Error::NoTitle));
    }

    #[test]
    fn finishing_marks_one_note() {
        let mut notes = Notes::default();
        notes.add("write the report").unwrap();
        notes.add("send it").unwrap();
        assert_eq!(notes.finish(1), Ok(()));
        assert_eq!(notes.finish(0), Err(Error::NoSuchNote(0)));
        assert_eq!(notes.finish(3), Err(Error::NoSuchNote(3)));
        assert_eq!(notes.render(), "[x] write the report\n[ ] send it\n");
    }
}
