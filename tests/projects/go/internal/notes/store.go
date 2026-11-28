// Package notes holds the notes of one running service.
package notes

import (
	"errors"
	"sync"
)

// ErrNoTitle is what Add answers for an empty title.
var ErrNoTitle = errors.New("a note needs a title")

// Note is one note; IDs start at 1 and follow the order of adding.
type Note struct {
	ID    int    `json:"id"`
	Title string `json:"title"`
	Done  bool   `json:"done"`
}

// Store keeps notes in memory and may be used from many goroutines.
type Store struct {
	mu    sync.Mutex
	items []Note
}

// Add keeps a new note and returns it.
func (s *Store) Add(title string) (Note, error) {
	if title == "" {
		return Note{}, ErrNoTitle
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	note := Note{ID: len(s.items) + 1, Title: title}
	s.items = append(s.items, note)
	return note, nil
}

// All returns a copy of every note, oldest first.
func (s *Store) All() []Note {
	s.mu.Lock()
	defer s.mu.Unlock()
	return append([]Note{}, s.items...)
}

// Finish marks a note done and reports whether there is one with that ID.
func (s *Store) Finish(id int) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	if id < 1 || id > len(s.items) {
		return false
	}
	s.items[id-1].Done = true
	return true
}
