import pytest

from notes.store import Store


def test_a_note_is_kept_in_the_order_it_was_added():
    store = Store()
    store.add("write the report")
    store.add("send it")
    assert [n["title"] for n in store.all()] == ["write the report", "send it"]


def test_a_note_with_no_title_is_refused():
    with pytest.raises(ValueError):
        Store().add("")


def test_finishing_marks_one_note():
    store = Store()
    first = store.add("write the report")
    store.add("send it")
    assert store.finish(first["id"]) is True
    assert [n["done"] for n in store.all()] == [True, False]
    assert store.finish(99) is False
