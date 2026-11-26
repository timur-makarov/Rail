"""Notes in a SQLite database."""

import sqlite3


class Store:
    def __init__(self, path: str = ":memory:") -> None:
        # One connection, used from the server's handler thread as well as the thread that made it.
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS notes"
            " (id INTEGER PRIMARY KEY, title TEXT NOT NULL, done INTEGER NOT NULL)"
        )

    def add(self, title: str) -> dict:
        if not title:
            raise ValueError("a note needs a title")
        with self.db:
            row = self.db.execute("INSERT INTO notes (title, done) VALUES (?, 0)", (title,))
        return {"id": row.lastrowid, "title": title, "done": False}

    def all(self) -> list[dict]:
        rows = self.db.execute("SELECT id, title, done FROM notes ORDER BY id").fetchall()
        return [{"id": i, "title": title, "done": bool(done)} for i, title, done in rows]

    def finish(self, note_id: int) -> bool:
        with self.db:
            changed = self.db.execute("UPDATE notes SET done = 1 WHERE id = ?", (note_id,))
        return changed.rowcount == 1
