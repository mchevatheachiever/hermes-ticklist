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
import export  # noqa: E402


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
        self.assertEqual(result["list"]["name"], "Ticklist")
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
        self.assertEqual(sorted(entry["name"] for entry in summary["lists"]), ["Jobs", "Shopping"])

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
        self.assertEqual([entry["name"] for entry in self.store.summary()["lists"]], ["Fresh"])

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

    def test_delete_list_removes_it_and_reports_the_loss(self):
        self.store.add_items("shop", ["a", "b"])
        self.store.add_items("jobs", ["c"])
        result = self.store.delete_list("shop")
        self.assertEqual(result["name"], "Shop")
        self.assertEqual(result["items"], 2)
        self.assertNotIn("shop", self.store.summary()["active"])
        self.assertEqual([e["id"] for e in self.store.summary()["lists"]], ["jobs"])

    def test_deleting_the_active_list_moves_active_elsewhere(self):
        self.store.add_items("shop", ["a"])
        self.store.add_items("jobs", ["b"])
        self.assertEqual(self.store.summary()["active"], "jobs")
        self.store.delete_list("jobs")
        self.assertEqual(self.store.summary()["active"], "shop")

    def test_deleting_the_last_list_empties_active(self):
        self.store.add_items("only", ["a"])
        core.ensure_seed(self.store)  # writes the marker: a used store, not a fresh one
        self.store.delete_list("only")
        summary = self.store.summary()
        self.assertEqual(summary["lists"], [])
        self.assertEqual(summary["active"], "")
        # and it must not resurrect the seed on the next call
        self.assertEqual(core.ensure_seed(self.store), "")

    def test_deleting_an_unknown_list_raises(self):
        self.store.add_items("shop", ["a"])
        with self.assertRaises(core.TickError):
            self.store.delete_list("nope")

    def test_counts(self):
        items = self.store.add_items(None, ["a", "b", "c"])["list"]["items"]
        self.store.set_done(None, items[0]["id"], True)
        entry = self.store.get_list()
        self.assertEqual(sum(1 for i in entry["items"] if i["done"]), 1)


class ReorderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = core.TickStore(Path(self.tmp.name))
        self.store.add_items("shop", ["a", "b", "c"])

    def tearDown(self):
        self.tmp.cleanup()

    def texts(self):
        return [item["text"] for item in self.store.get_list("shop")["items"]]

    def ids(self):
        return [item["id"] for item in self.store.get_list("shop")["items"]]

    def test_reorder_sets_the_order(self):
        ids = self.ids()
        self.store.reorder("shop", list(reversed(ids)))
        self.assertEqual(self.texts(), ["c", "b", "a"])

    def test_reorder_survives_a_reload(self):
        ids = self.ids()
        self.store.reorder("shop", [ids[1], ids[2], ids[0]])
        self.assertEqual(core.TickStore(Path(self.tmp.name)).get_list("shop")["items"][0]["text"], "b")

    def test_a_partial_order_is_refused(self):
        with self.assertRaises(core.TickError):
            self.store.reorder("shop", self.ids()[:2])
        self.assertEqual(self.texts(), ["a", "b", "c"])

    def test_a_duplicated_id_is_refused(self):
        ids = self.ids()
        with self.assertRaises(core.TickError):
            self.store.reorder("shop", [ids[0], ids[0], ids[1]])


class ExportTest(unittest.TestCase):
    def setUp(self):
        self.entry = {
            "name": "Shop",
            "items": [
                {"id": "a1", "text": 'brackets, 2"', "done": False, "created": 1.0, "done_at": None},
                {"id": "b2", "text": "paint", "done": True, "created": 2.0, "done_at": 3.0},
            ],
            "created_at": 1.0,
            "updated_at": 3.0,
        }

    def test_text(self):
        self.assertEqual(
            export.build_text(self.entry),
            'Shop — 1/2 done\n\n[ ] brackets, 2"\n[x] paint\n',
        )

    def test_markdown_is_a_task_list(self):
        body = export.build_markdown(self.entry)
        self.assertIn("# Shop", body)
        self.assertIn("- [ ] brackets", body)
        self.assertIn("- [x] paint", body)

    def test_csv_quotes_and_has_a_header(self):
        body = export.build_csv(self.entry)
        self.assertTrue(body.startswith("done,text,created,done_at,id"))
        self.assertIn('"brackets, 2"""', body)
        self.assertEqual(len(body.strip().splitlines()), 3)

    def test_json_round_trips(self):
        self.assertEqual(json.loads(export.build_json(self.entry)), self.entry)

    def test_unknown_format_is_refused(self):
        with self.assertRaises(ValueError):
            export.build(self.entry, "xlsx")


class SeedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = core.TickStore(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_store_gets_the_example_list(self):
        self.assertEqual(core.ensure_seed(self.store), core.SEED_LIST)
        entry = self.store.get_list(core.SEED_LIST)
        self.assertTrue(entry["items"])
        self.assertTrue(any(item["done"] for item in entry["items"]))

    def test_seeds_only_once(self):
        core.ensure_seed(self.store)
        self.assertEqual(core.ensure_seed(self.store), "")
        self.assertEqual(len(self.store.summary()["lists"]), 1)

    def test_a_used_store_is_not_seeded(self):
        self.store.add_items("Real work", ["brackets"])
        self.assertEqual(core.ensure_seed(self.store), "")
        self.assertEqual([e["name"] for e in self.store.summary()["lists"]], ["Real work"])

    def test_deleting_every_list_does_not_resurrect_the_demo(self):
        core.ensure_seed(self.store)
        state = self.store.read()
        state["lists"] = {}
        state["active"] = ""
        self.store.write(state)
        self.assertEqual(core.ensure_seed(self.store), "")
        self.assertEqual(self.store.summary()["lists"], [])


class NameTest(unittest.TestCase):
    def test_titles_capitalise(self):
        self.assertEqual(core.clean_name("vehicles"), "Vehicles")
        self.assertEqual(core.clean_name("site work #2"), "Site work #2")
        self.assertEqual(core.clean_name("a"), "A")

    def test_names_the_user_chose_keep_their_case(self):
        self.assertEqual(core.clean_name("DIY bits"), "DIY bits")
        self.assertEqual(core.clean_name("iPad list"), "iPad list")
        self.assertEqual(core.clean_name("123 numbers"), "123 numbers")

    def test_capitalising_does_not_change_the_key(self):
        self.assertEqual(core.list_key("vehicles"), core.list_key("Vehicles"))


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
