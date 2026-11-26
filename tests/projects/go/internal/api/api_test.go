package api

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"example.com/notes/internal/notes"
)

// call drives the API over a real socket and returns the status and the body.
func call(t *testing.T, method, url, body string) (int, string) {
	t.Helper()
	request, err := http.NewRequest(method, url, strings.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = response.Body.Close() }()
	text, err := io.ReadAll(response.Body)
	if err != nil {
		t.Fatal(err)
	}
	return response.StatusCode, strings.TrimSpace(string(text))
}

func TestTheAPIOverASocket(t *testing.T) {
	server := httptest.NewServer(Handler(&notes.Store{}))
	defer server.Close()

	cases := []struct {
		method, path, body string
		status             int
		want               string
	}{
		{"POST", "/notes", `{"title":"write the report"}`, 201, `{"id":1,"title":"write the report","done":false}`},
		{"POST", "/notes", `{}`, 400, `{"error":"a note needs a title"}`},
		{"POST", "/notes", `not json`, 400, `{"error":"the body is not JSON"}`},
		{"POST", "/notes/1/done", ``, 200, `{"done":true}`},
		{"POST", "/notes/7/done", ``, 404, `{"done":false}`},
		{"GET", "/notes", ``, 200, `[{"id":1,"title":"write the report","done":true}]`},
	}
	for _, c := range cases {
		status, got := call(t, c.method, server.URL+c.path, c.body)
		if status != c.status || got != c.want {
			t.Errorf("%s %s %s: got %d %s, want %d %s", c.method, c.path, c.body, status, got, c.status, c.want)
		}
	}
	if status, _ := call(t, "GET", server.URL+"/nowhere", ""); status != 404 {
		t.Errorf("GET /nowhere: got %d, want 404", status)
	}
}
