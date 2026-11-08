"""API surface test for ticklist — run with a venv that has FastAPI."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    FastAPI = None
    TestClient = None


def load_api():
    spec = importlib.util.spec_from_file_location(
        "ticklist_api", ROOT / "dashboard" / "plugin_api.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["ticklist_api"] = module
    spec.loader.exec_module(module)
    return module


@unittest.skipIf(TestClient is None, "fastapi not installed")
class ApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.api = load_api()
        self.patch = mock.patch.object(
            self.api.core, "plugin_data_dir", lambda name="ticklist": Path(self.tmp.name)
        )
        self.patch.start()
        app = FastAPI()
        app.include_router(self.api.router, prefix="/api/plugins/ticklist")
        self.client = TestClient(app)

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_health(self):
        self.assertEqual(self.client.get("/api/plugins/ticklist/health").json()["ok"], True)

    def test_empty_state(self):
        body = self.client.get("/api/plugins/ticklist/lists").json()
        self.assertEqual(body["lists"], [])

    def test_add_then_tick(self):
        created = self.client.post(
            "/api/plugins/ticklist/lists", json={"items": ["brackets", "screws"]}
        )
        self.assertEqual(created.status_code, 200, created.text)
        state = created.json()
        self.assertEqual(state["lists"][0]["total"], 2)

        item_id = state["lists"][0]["items"][0]["id"]
        ticked = self.client.patch(f"/api/plugins/ticklist/items/{item_id}", json={"done": True})
        self.assertEqual(ticked.status_code, 200, ticked.text)
        self.assertEqual(ticked.json()["lists"][0]["done"], 1)

    def test_tick_names_its_list_not_the_active_one(self):
        # The pane ticks a tab that isn't the active list; without ?list= the
        # route searched the active list and answered 404.
        first = self.client.post("/api/plugins/ticklist/lists", json={"items": ["mogami"], "list": "audio"}).json()
        self.client.post("/api/plugins/ticklist/lists", json={"items": ["vehicles"], "list": "cars"})
        item_id = first["lists"][0]["items"][0]["id"]

        blind = self.client.patch(f"/api/plugins/ticklist/items/{item_id}", json={"done": True})
        self.assertEqual(blind.status_code, 404)

        scoped = self.client.patch(
            f"/api/plugins/ticklist/items/{item_id}?list=audio", json={"done": True}
        )
        self.assertEqual(scoped.status_code, 200, scoped.text)
        audio = next(entry for entry in scoped.json()["lists"] if entry["id"] == "audio")
        self.assertEqual(audio["done"], 1)

    def test_delete_list_route(self):
        self.client.post("/api/plugins/ticklist/lists", json={"items": ["a", "b"], "list": "shop"})
        self.client.post("/api/plugins/ticklist/lists", json={"items": ["c"], "list": "jobs"})
        response = self.client.delete("/api/plugins/ticklist/lists/shop")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["deleted"]["items"], 2)
        self.assertEqual([entry["id"] for entry in body["lists"]], ["jobs"])
        self.assertEqual(self.client.delete("/api/plugins/ticklist/lists/shop").status_code, 404)

    def test_pin_route(self):
        self.client.post("/api/plugins/ticklist/lists", json={"items": ["a"], "list": "work"})
        self.client.post("/api/plugins/ticklist/lists", json={"items": ["b"], "list": "shop"})
        response = self.client.patch("/api/plugins/ticklist/lists/shop", json={"pinned": True})
        self.assertEqual(response.status_code, 200, response.text)
        first = response.json()["lists"][0]
        self.assertEqual(first["id"], "shop")
        self.assertTrue(first["pinned"])
        self.assertEqual(
            self.client.patch("/api/plugins/ticklist/lists/nope", json={"pinned": True}).status_code,
            404,
        )

    def test_clear_targets_the_named_list(self):
        self.client.post("/api/plugins/ticklist/lists", json={"items": ["a", "b"], "list": "shop"})
        other = self.client.post(
            "/api/plugins/ticklist/lists", json={"items": ["c"], "list": "jobs"}
        ).json()
        jobs_entry = next(entry for entry in other["lists"] if entry["id"] == "jobs")
        item_id = jobs_entry["items"][0]["id"]
        self.client.patch(f"/api/plugins/ticklist/items/{item_id}?list=jobs", json={"done": True})
        cleared = self.client.post("/api/plugins/ticklist/clear?list=jobs", json={"done_only": True})
        self.assertEqual(cleared.status_code, 200, cleared.text)
        jobs = next(entry for entry in cleared.json()["lists"] if entry["id"] == "jobs")
        shop = next(entry for entry in cleared.json()["lists"] if entry["id"] == "shop")
        self.assertEqual(jobs["total"], 0)
        self.assertEqual(shop["total"], 2)  # untouched

    def test_reorder_route(self):
        state = self.client.post("/api/plugins/ticklist/lists", json={"items": ["a", "b", "c"]}).json()
        ids = [item["id"] for item in state["lists"][0]["items"]]
        response = self.client.patch(
            "/api/plugins/ticklist/lists/ticklist/order", json={"ids": list(reversed(ids))}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([i["text"] for i in response.json()["lists"][0]["items"]], ["c", "b", "a"])

        bad = self.client.patch("/api/plugins/ticklist/lists/ticklist/order", json={"ids": ids[:1]})
        self.assertEqual(bad.status_code, 400)

    def test_export_route(self):
        self.client.post("/api/plugins/ticklist/lists", json={"items": ["a", "b"], "list": "shop"})
        for fmt, needle in (("txt", "[ ] a"), ("md", "- [ ] a"), ("csv", "done,text"), ("json", '"items"')):
            body = self.client.get(f"/api/plugins/ticklist/lists/shop/export?fmt={fmt}").json()
            self.assertIn(needle, body["content"], fmt)
            self.assertTrue(body["filename"].endswith("." + ("md" if fmt == "md" else fmt)))
        self.assertEqual(
            self.client.get("/api/plugins/ticklist/lists/shop/export?fmt=xlsx").status_code, 400
        )
        self.assertEqual(
            self.client.get("/api/plugins/ticklist/lists/nope/export").status_code, 404
        )

    def test_remove(self):
        state = self.client.post(
            "/api/plugins/ticklist/lists", json={"items": ["a", "b"]}
        ).json()
        item_id = state["lists"][0]["items"][0]["id"]
        removed = self.client.delete(f"/api/plugins/ticklist/items/{item_id}")
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertEqual(removed.json()["lists"][0]["total"], 1)

    def test_clear_done_only(self):
        state = self.client.post(
            "/api/plugins/ticklist/lists", json={"items": ["a", "b"]}
        ).json()
        item_id = state["lists"][0]["items"][0]["id"]
        self.client.patch(f"/api/plugins/ticklist/items/{item_id}", json={"done": True})
        cleared = self.client.post("/api/plugins/ticklist/clear", json={"done_only": True})
        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertEqual(cleared.json()["lists"][0]["total"], 1)

    def test_bad_payload_is_400(self):
        response = self.client.post("/api/plugins/ticklist/lists", json={"items": []})
        self.assertEqual(response.status_code, 400)

    def test_unknown_item_is_404(self):
        self.client.post("/api/plugins/ticklist/lists", json={"items": ["a"]})
        response = self.client.patch("/api/plugins/ticklist/items/nope", json={"done": True})
        self.assertEqual(response.status_code, 404)



    def test_health_does_not_leak_the_store_path(self):
        # Driven through the client: `health()` is async, so calling it directly
        # hands back a coroutine and the assertion passes on nothing.
        original = self.api.core.TickStore.read

        def boom(self):
            raise OSError("/home/someone/.hermes/plugin-data/ticklist/lists.json")

        self.api.core.TickStore.read = boom
        try:
            body = self.client.get("/api/plugins/ticklist/health").json()
        finally:
            self.api.core.TickStore.read = original
        self.assertFalse(body["ok"])
        self.assertNotIn("/home", body["error"])

    def test_inactive_lists_ship_without_rows(self):
        self.client.post("/api/plugins/ticklist/lists", json={"items": ["a"], "list": "one"})
        self.client.post("/api/plugins/ticklist/lists", json={"items": ["b", "c"], "list": "two"})
        body = self.client.get("/api/plugins/ticklist/lists").json()
        by_name = {entry["id"]: entry for entry in body["lists"]}
        self.assertNotIn("items", by_name["one"])
        self.assertIn("items", by_name["two"])
        self.assertEqual(by_name["one"]["total"], 1)

    def test_single_list_route_returns_rows(self):
        self.client.post("/api/plugins/ticklist/lists", json={"items": ["a", "b"], "list": "shop"})
        self.client.post("/api/plugins/ticklist/lists", json={"items": ["c"], "list": "other"})
        body = self.client.get("/api/plugins/ticklist/lists/shop").json()
        self.assertEqual(body["list"]["id"], "shop")
        self.assertEqual(len(body["list"]["items"]), 2)
        missing = self.client.get("/api/plugins/ticklist/lists/nope")
        self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
