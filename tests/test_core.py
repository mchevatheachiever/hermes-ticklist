"""Tests for ticklist core + text rendering. stdlib only."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import art  # noqa: E402
import core  # noqa: E402


class TextTest(unittest.TestCase):
    def test_trims_and_rejects_empty(self):
        self.assertEqual(core.clean_text("  buy milk  "), "buy milk")
        with self.assertRaises(core.TickError):
            core.clean_text("   ")

    def test_strips_control_characters(self):
        self.assertEqual(core.clean_text("a\x00b\nc"), "a b c")

    def test_caps_length(self):
        self.assertEqual(len(core.clean_text("x" * 500)), core.MAX_TEXT_CHARS)

    def test_accepts_multiline_string(self):
        items = core.normalise_items("one\ntwo\n\nthree")
        self.assertEqual([i["text"] for i in items], ["one", "two", "three"])

    def test_duplicates_collapse(self):
        items = core.normalise_items(["Milk", "milk", "Eggs"])
        self.assertEqual([i["text"] for i in items], ["Milk", "Eggs"])

    def test_done_flag_from_dicts(self):
        items = core.normalise_items([{"text": "a", "done": True}, "b"])
        self.assertEqual([i["done"] for i in items], [True, False])


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = core.TickStore(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_creates_list(self):
        result = self.store.add_items(None, ["brackets", "screws"])
        self.assertEqual(result["list"]["name"], "ticklist")
        self.assertEqual(len(result["list"]["items"]), 2)
        self.assertTrue(all(not i["done"] for i in result["list"]["items"]))

    def test_add_is_idempotent(self):
        self.store.add_items(None, ["a", "b"])
        again = self.store.add_items(None, ["b", "c"])
        self.assertEqual([i["text"] for i in again["added"]], ["c"])
        self.assertEqual(len(again["list"]["items"]), 3)

    def test_tick_by_text(self):
        self.store.add_items(None, ["brackets"])
        result = self.store.set_done(None, "brackets", True)
        self.assertTrue(result["item"]["done"])
        self.assertIsNotNone(result["item"]["done_at"])

    def test_tick_by_id(self):
        added = self.store.add_items(None, ["brackets"])["list"]["items"][0]
        result = self.store.set_done(None, added["id"], True)
        self.assertTrue(result["item"]["done"])

    def test_untick_clears_done_at(self):
        item = self.store.add_items(None, ["x"])["list"]["items"][0]
        self.store.set_done(None, item["id"], True)
        result = self.store.set_done(None, item["id"], False)
        self.assertFalse(result["item"]["done"])
        self.assertIsNone(result["item"]["done_at"])

    def test_unique_substring_resolves(self):
        self.store.add_items(None, ["buy red paint", "buy blue paint"])
        result = self.store.set_done(None, "red paint", True)
        self.assertEqual(result["item"]["text"], "buy red paint")

    def test_ambiguous_reference_is_refused(self):
        self.store.add_items(None, ["buy red paint", "buy blue paint"])
        with self.assertRaises(core.TickError) as ctx:
            self.store.set_done(None, "paint", True)
        self.assertIn("matches several", str(ctx.exception))

    def test_unknown_item_raises(self):
        self.store.add_items(None, ["a"])
        with self.assertRaises(core.TickError):
            self.store.set_done(None, "zzz", True)

    def test_remove(self):
        self.store.add_items(None, ["a", "b"])
        result = self.store.remove(None, "a")
        self.assertEqual(result["removed"], 1)
        self.assertEqual([i["text"] for i in result["list"]["items"]], ["b"])

    def test_clear_done_only(self):
        items = self.store.add_items(None, ["a", "b", "c"])["list"]["items"]
        self.store.set_done(None, items[1]["id"], True)
        result = self.store.clear(None, done_only=True)
        self.assertEqual([i["text"] for i in result["list"]["items"]], ["a", "c"])

    def test_separate_lists(self):
        self.store.add_items("shopping", ["milk"])
        self.store.add_items("jobs", ["fence"])
        summary = self.store.summary()
        self.assertEqual(sorted(entry["name"] for entry in summary["lists"]), ["jobs", "shopping"])

    def test_persisted_json_shape(self):
        self.store.add_items(None, ["a"])
        raw = json.loads((Path(self.tmp.name) / "lists.json").read_text())
        self.assertEqual(raw["version"], 1)
        self.assertIn("ticklist", raw["lists"])

    def test_corrupt_file_falls_back(self):
        (Path(self.tmp.name) / "lists.json").write_text("{nope")
        self.assertEqual(self.store.summary()["lists"], [])

    def test_corrupt_file_is_quarantined_not_destroyed(self):
        # An empty state returned from a corrupt read must never be allowed to
        # overwrite the only copy of the user's items on the next write.
        path = Path(self.tmp.name) / "lists.json"
        path.write_text('{"version": 1, "lists": {"shop": {"items": [')  # truncated
        self.assertEqual(self.store.summary()["lists"], [])

        backups = list(Path(self.tmp.name).glob("lists.json.corrupt-*"))
        self.assertEqual(len(backups), 1, backups)
        self.assertIn("shop", backups[0].read_text())

        self.store.add_items("fresh", ["milk"])
        self.assertEqual(len(backups[0].read_text()) > 0, True)
        self.assertEqual([entry["name"] for entry in self.store.summary()["lists"]], ["fresh"])

    def test_long_names_do_not_collide(self):
        a = "Build the whole fence along the north boundary of the property line A"
        b = "Build the whole fence along the north boundary of the property line B"
        self.assertNotEqual(core.slugify(a), core.slugify(b))
        self.store.add_items(a, ["posts"])
        self.store.add_items(b, ["rails"])
        ids = [entry["id"] for entry in self.store.summary()["lists"]]
        self.assertEqual(len(ids), 2, ids)
        self.assertNotEqual(ids[0], ids[1])
        # each list kept its own items
        first = self.store.get_list(a)
        second = self.store.get_list(b)
        self.assertEqual([i["text"] for i in first["items"]], ["posts"])
        self.assertEqual([i["text"] for i in second["items"]], ["rails"])

    def test_short_names_keep_a_readable_slug(self):
        self.assertEqual(core.slugify("Site work #2"), "site-work-2")

    def test_counts(self):
        items = self.store.add_items(None, ["a", "b", "c"])["list"]["items"]
        self.store.set_done(None, items[0]["id"], True)
        entry = self.store.get_list()
        self.assertEqual(sum(1 for i in entry["items"] if i["done"]), 1)


class PayloadTest(unittest.TestCase):
    def test_mapping_items_are_refused(self):
        # A model posting {"text": "milk"} iterates a dict's keys and would store
        # an item literally named "text".
        with self.assertRaises(core.TickError) as caught:
            core.normalise_items({"text": "milk"})
        self.assertIn("wrap", str(caught.exception))

    def test_list_of_one_mapping_is_accepted(self):
        items = core.normalise_items([{"text": "milk"}])
        self.assertEqual([item["text"] for item in items], ["milk"])


class RenderTest(unittest.TestCase):
    def entry(self):
        items = core.normalise_items(["brackets", "screws", "paint"])
        items[1]["done"] = True
        return {"name": "shop", "items": items}

    def test_every_line_starts_at_column_zero(self):
        for line in art.render_list(self.entry()).splitlines():
            if line:
                self.assertFalse(line.startswith(" "), repr(line))

    def test_boxes_and_progress(self):
        text = art.render_list(self.entry())
        self.assertIn("[x] screws", text)
        self.assertIn("[ ] brackets", text)
        self.assertIn("1/3 done", text)

    def test_empty_list(self):
        text = art.render_list({"name": "x", "items": []})
        self.assertIn("0/0 done", text)
        self.assertIn("empty", text)

    def test_unticked_sorted_before_ticked(self):
        entry = self.entry()
        text = art.render_list(entry)
        lines = [line for line in text.splitlines() if line.startswith("[")]
        self.assertEqual(lines[0], "[ ] brackets")
        self.assertEqual(lines[-1], "[x] screws")

    def test_long_labels_are_ellipsised_not_cut(self):
        entry = self.entry()
        entry["items"][0]["text"] = "x" * 200
        text = art.render_list(entry)
        self.assertIn("…", text)
        self.assertNotIn("x" * 60, text)

    def test_change_line(self):
        self.assertIn("ticked", art.render_change({"text": "a", "done": True}))
        self.assertIn("unticked", art.render_change({"text": "a", "done": False}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
