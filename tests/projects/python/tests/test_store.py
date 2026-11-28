import unittest

from notes.store import Store


class StoreTest(unittest.TestCase):
    def test_a_note_is_kept_in_the_order_it_was_added(self) -> None:
        store = Store()
        store.add("write the report")
        store.add("send it")
        self.assertEqual([n["title"] for n in store.all()], ["write the report", "send it"])

    def test_a_note_with_no_title_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            Store().add("")

    def test_finishing_marks_one_note(self) -> None:
        store = Store()
        first = store.add("write the report")
        store.add("send it")
        self.assertIs(store.finish(first["id"]), True)
        self.assertEqual([n["done"] for n in store.all()], [True, False])
        self.assertIs(store.finish(99), False)
