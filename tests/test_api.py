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


if __name__ == "__main__":
    unittest.main(verbosity=2)
