// Package api is the HTTP API over a store: GET and POST /notes, POST /notes/{id}/done.
package api

import (
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"strconv"

	"example.com/notes/internal/notes"
)

func answer(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	// The status is sent already; a client that went away is all that can fail here.
	_ = json.NewEncoder(w).Encode(body)
}

// Handler serves the API over the store.
func Handler(store *notes.Store) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /notes", func(w http.ResponseWriter, _ *http.Request) {
		// A fault to switch on from outside, for a check that drives the running service: the list comes back empty.
		if os.Getenv("NOTES_FAULT") != "" {
			answer(w, http.StatusOK, []notes.Note{})
			return
		}
		answer(w, http.StatusOK, store.All())
	})
	mux.HandleFunc("POST /notes", func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			Title string `json:"title"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			answer(w, http.StatusBadRequest, map[string]string{"error": "the body is not JSON"})
			return
		}
		note, err := store.Add(body.Title)
		if errors.Is(err, notes.ErrNoTitle) {
			answer(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
			return
		}
		answer(w, http.StatusCreated, note)
	})
	mux.HandleFunc("POST /notes/{id}/done", func(w http.ResponseWriter, r *http.Request) {
		id, err := strconv.Atoi(r.PathValue("id"))
		found := err == nil && store.Finish(id)
		status := http.StatusOK
		if !found {
			status = http.StatusNotFound
		}
		answer(w, status, map[string]bool{"done": found})
	})
	return mux
}
