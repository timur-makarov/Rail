package main

import (
	"net/http/httptest"
	"strings"
	"testing"

	"example.com/notes/internal/api"
	"example.com/notes/internal/notes"
)

// The command as a client of a running server, each call as a person would type it.
func TestTheCommandAgainstARunningServer(t *testing.T) {
	server := httptest.NewServer(api.Handler(&notes.Store{}))
	defer server.Close()

	var out strings.Builder
	for _, args := range [][]string{
		{"add", server.URL, "write the report"},
		{"add", server.URL, "send it"},
		{"done", server.URL, "1"},
		{"list", server.URL},
	} {
		if err := run(args, &out); err != nil {
			t.Fatalf("notes %s: %v", strings.Join(args, " "), err)
		}
	}
	want := "added 1\nadded 2\ndone 1\n[x] write the report\n[ ] send it\n"
	if out.String() != want {
		t.Fatalf("got %q, want %q", out.String(), want)
	}
}

func TestAMistakeSaysWhatIsWrong(t *testing.T) {
	server := httptest.NewServer(api.Handler(&notes.Store{}))
	defer server.Close()

	var out strings.Builder
	for args, want := range map[string]string{
		"done " + server.URL + " 4": "there is no note 4",
		"add " + server.URL + " ":   "a note needs a title",
		"remove":                    usage,
	} {
		err := run(strings.Split(args, " "), &out)
		if err == nil || err.Error() != want {
			t.Errorf("notes %s: got %v, want %q", args, err, want)
		}
	}
}
