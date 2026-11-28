// Command notes serves the notes API, or calls a running one.
//
//	notes serve [ADDRESS]
//	notes add|done|list URL [TITLE|ID]
package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"

	"example.com/notes/internal/api"
	"example.com/notes/internal/notes"
)

const usage = "usage: notes serve [ADDRESS] | add URL TITLE | done URL ID | list URL"

// call sends one request to a running server and returns its notes, or the error it answered.
func call(method, url string, body any, into any) error {
	var sent io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return err
		}
		sent = strings.NewReader(string(data))
	}
	request, err := http.NewRequest(method, url, sent)
	if err != nil {
		return err
	}
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		return err
	}
	defer func() { _ = response.Body.Close() }()
	if response.StatusCode >= 400 {
		var failed struct {
			Error string `json:"error"`
		}
		if err := json.NewDecoder(response.Body).Decode(&failed); err != nil || failed.Error == "" {
			return fmt.Errorf("the server answered %d", response.StatusCode)
		}
		return errors.New(failed.Error)
	}
	return json.NewDecoder(response.Body).Decode(into)
}

func run(args []string, out io.Writer) error {
	switch {
	case len(args) >= 1 && len(args) <= 2 && args[0] == "serve":
		address := "127.0.0.1:8000"
		if len(args) == 2 {
			address = args[1]
		}
		return http.ListenAndServe(address, api.Handler(&notes.Store{}))
	case len(args) == 3 && args[0] == "add":
		var note notes.Note
		if err := call("POST", args[1]+"/notes", map[string]string{"title": args[2]}, &note); err != nil {
			return err
		}
		_, err := fmt.Fprintf(out, "added %d\n", note.ID)
		return err
	case len(args) == 3 && args[0] == "done":
		var done map[string]bool
		if err := call("POST", args[1]+"/notes/"+args[2]+"/done", nil, &done); err != nil {
			return fmt.Errorf("there is no note %s", args[2])
		}
		_, err := fmt.Fprintf(out, "done %s\n", args[2])
		return err
	case len(args) == 2 && args[0] == "list":
		var all []notes.Note
		if err := call("GET", args[1]+"/notes", nil, &all); err != nil {
			return err
		}
		for _, note := range all {
			mark := " "
			if note.Done {
				mark = "x"
			}
			if _, err := fmt.Fprintf(out, "[%s] %s\n", mark, note.Title); err != nil {
				return err
			}
		}
		return nil
	}
	return errors.New(usage)
}

func main() {
	if err := run(os.Args[1:], os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
}
