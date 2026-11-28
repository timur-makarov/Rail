package notes

import (
	"errors"
	"sync"
	"testing"
)

func TestNotesAreKeptInTheOrderTheyWereAdded(t *testing.T) {
	var store Store
	for _, title := range []string{"write the report", "send it"} {
		if _, err := store.Add(title); err != nil {
			t.Fatal(err)
		}
	}
	all := store.All()
	if len(all) != 2 || all[0].Title != "write the report" || all[1].ID != 2 {
		t.Fatalf("got %+v", all)
	}
	if _, err := store.Add(""); !errors.Is(err, ErrNoTitle) {
		t.Fatalf("an empty title gave %v", err)
	}
}

func TestFinishingMarksOneNote(t *testing.T) {
	var store Store
	_, _ = store.Add("write the report")
	_, _ = store.Add("send it")
	if !store.Finish(1) || store.Finish(0) || store.Finish(3) {
		t.Fatal("Finish answered wrongly")
	}
	if all := store.All(); !all[0].Done || all[1].Done {
		t.Fatalf("got %+v", all)
	}
}

func TestNotesAddedAtOnceEachGetTheirOwnID(t *testing.T) {
	var store Store
	var wait sync.WaitGroup
	for i := 0; i < 50; i++ {
		wait.Add(1)
		go func() {
			defer wait.Done()
			_, _ = store.Add("a note")
		}()
	}
	wait.Wait()
	seen := map[int]bool{}
	for _, note := range store.All() {
		seen[note.ID] = true
	}
	if len(seen) != 50 {
		t.Fatalf("50 notes got %d different IDs", len(seen))
	}
}
