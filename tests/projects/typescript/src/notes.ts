export type Note = { id: number; title: string; done: boolean };

export class Notes {
  private items: Note[] = [];

  add(title: string): Note {
    if (title === "") {
      throw new Error("a note needs a title");
    }
    const note: Note = { id: this.items.length + 1, title, done: false };
    this.items.push(note);
    return note;
  }

  all(): Note[] {
    return this.items.map((note) => ({ ...note }));
  }

  finish(id: number): boolean {
    const note = this.items.find((item) => item.id === id);
    if (note === undefined) {
      return false;
    }
    note.done = true;
    return true;
  }
}
