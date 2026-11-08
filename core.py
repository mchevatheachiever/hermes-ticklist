"""TickList core — the checklist store, shared by the tools and the API half.

One list per name (default ``ticklist``), items are ``{id, text, done, created,
done_at}``. State lives in ``<hermes home>/plugin-data/ticklist/lists.json`` and
is written atomically under an advisory lock, so the pane and the agent can both
write without truncating each other.

No network, no credentials, stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
import time
from contextlib import contextmanager
from typing import Any, Iterable, Iterator, Sequence

try:  # POSIX advisory locking; degrades to no lock on Windows.
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

SCHEMA_VERSION = 1
MAX_ITEMS = 2000
MAX_TEXT_CHARS = 240
MAX_NAME_CHARS = 60
MAX_LISTS = 50

_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


class TickError(ValueError):
    """Bad user input; callers turn this into a tool_error or a 400."""


def plugin_data_dir(name: str = "ticklist"):
    from plugins.plugin_storage import plugin_data_dir as _dir

    return _dir(name)


# --------------------------------------------------------------------------- #
# normalisation
# --------------------------------------------------------------------------- #


def clean_text(raw: Any) -> str:
    if not isinstance(raw, str):
        raise TickError("an item needs text")
    text = _CTRL_RE.sub(" ", raw).strip()
    if not text:
        raise TickError("item text cannot be empty")
    return text[:MAX_TEXT_CHARS]


def clean_name(raw: Any, *, default: str = "ticklist") -> str:
    if raw is None:
        return default
    if not isinstance(raw, str):
        raise TickError("list name must be text")
    text = _CTRL_RE.sub(" ", raw).strip()
    return (text or default)[:MAX_NAME_CHARS]


def slugify(name: str) -> str:
    slug = _SLUG_RE.sub("-", str(name).strip().lower()).strip("-")[:48]
    return slug or "ticklist"


def new_id() -> str:
    return secrets.token_hex(4)


def normalise_items(raw: Any) -> list[dict[str, Any]]:
    """Accept ``["a", "b"]`` or ``[{"text": "a", "done": true}]``.

    Duplicate texts collapse onto the first occurrence (case-insensitive): two
    identical rows are indistinguishable on screen and would drift apart.
    """
    if isinstance(raw, str):
        raw = [line for line in raw.splitlines() if line.strip()]
    if not isinstance(raw, Iterable):
        raise TickError("items must be a list of texts")

    seen: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    now = time.time()
    for entry in raw:
        if isinstance(entry, dict):
            text = clean_text(entry.get("text", entry.get("label", entry.get("content"))))
            done = bool(entry.get("done", entry.get("checked", False)))
        else:
            text = clean_text(entry)
            done = False
        key = text.casefold()
        if key in seen:
            continue
        seen[key] = {
            "id": new_id(),
            "text": text,
            "done": done,
            "created": now,
            "done_at": now if done else None,
        }
        order.append(key)
        if len(order) > MAX_ITEMS:
            raise TickError(f"a list holds at most {MAX_ITEMS} items")
    if not order:
        raise TickError("a list needs at least one item")
    return [seen[key] for key in order]


# --------------------------------------------------------------------------- #
# store
# --------------------------------------------------------------------------- #


def _empty_state() -> dict[str, Any]:
    return {"version": SCHEMA_VERSION, "active": "", "lists": {}}


class TickStore:
    """JSON-backed, lock-guarded checklist store."""

    def __init__(self, root=None):
        self.root = root if root is not None else plugin_data_dir("ticklist")
        self.path = self.root / "lists.json"
        self.lock_path = self.root / "lists.lock"

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True)
        handle = open(self.lock_path, "a+")
        try:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            try:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()

    def read(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return _empty_state()
        if not isinstance(raw, dict):
            return _empty_state()
        state = _empty_state()
        state["active"] = str(raw.get("active") or "")
        lists = raw.get("lists")
        if isinstance(lists, dict):
            for key, entry in lists.items():
                clean = self._clean_list(key, entry)
                if clean is not None:
                    state["lists"][key] = clean
        if state["active"] not in state["lists"]:
            state["active"] = next(iter(state["lists"]), "")
        return state

    @staticmethod
    def _clean_list(key: str, entry: Any) -> dict[str, Any] | None:
        if not isinstance(entry, dict):
            return None
        items = []
        for item in entry.get("items") or []:
            if not isinstance(item, dict):
                continue
            try:
                text = clean_text(item.get("text"))
            except TickError:
                continue
            items.append(
                {
                    "id": str(item.get("id") or new_id())[:16],
                    "text": text,
                    "done": bool(item.get("done")),
                    "created": float(item.get("created") or 0) or time.time(),
                    "done_at": item.get("done_at"),
                }
            )
        return {
            "id": key,
            "name": clean_name(entry.get("name"), default=key),
            "items": items[:MAX_ITEMS],
            "created_at": float(entry.get("created_at") or 0) or time.time(),
            "updated_at": float(entry.get("updated_at") or 0) or time.time(),
        }

    def write(self, state: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(state, indent=2, ensure_ascii=False)
        fd, tmp = tempfile.mkstemp(dir=str(self.root), prefix=".lists-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    # -- lists ------------------------------------------------------------- #

    def get_list(self, name: str | None = None) -> dict[str, Any]:
        state = self.read()
        lists = state["lists"]
        if not lists:
            raise TickError("no list exists yet")
        key = state["active"] if name is None else slugify(clean_name(name))
        entry = lists.get(key)
        if entry is None:
            known = ", ".join(sorted(entry["name"] for entry in lists.values()))
            raise TickError(f"no list called {name!r}; known lists: {known}")
        return entry

    def ensure_list(self, name: str | None = None) -> dict[str, Any]:
        display = clean_name(name)
        key = slugify(display)
        with self._locked():
            state = self.read()
            entry = state["lists"].get(key)
            if entry is None:
                if len(state["lists"]) >= MAX_LISTS:
                    raise TickError(f"at most {MAX_LISTS} lists")
                now = time.time()
                entry = {
                    "id": key,
                    "name": display,
                    "items": [],
                    "created_at": now,
                    "updated_at": now,
                }
                state["lists"][key] = entry
            state["active"] = key
            self.write(state)
        return entry

    def add_items(self, name: str | None, raw_items: Any, *, dedupe: bool = True) -> dict[str, Any]:
        incoming = normalise_items(raw_items)
        entry = self.ensure_list(name)
        key = entry["id"]
        with self._locked():
            state = self.read()
            current = state["lists"][key]
            existing = {item["text"].casefold() for item in current["items"]}
            added: list[dict[str, Any]] = []
            for item in incoming:
                if dedupe and item["text"].casefold() in existing:
                    continue
                existing.add(item["text"].casefold())
                added.append(item)
            if len(current["items"]) + len(added) > MAX_ITEMS:
                raise TickError(f"a list holds at most {MAX_ITEMS} items")
            current["items"].extend(added)
            current["updated_at"] = time.time()
            self.write(state)
        return {"list": current, "added": added}

    def set_done(self, name: str | None, reference: str, done: bool) -> dict[str, Any]:
        """Tick/untick by id or by text. Returns the item and the whole list."""
        ref = str(reference or "").strip()
        if not ref:
            raise TickError("an item id or text is required")
        entry = self.get_list(name)
        key = entry["id"]
        with self._locked():
            state = self.read()
            current = state["lists"][key]
            target = None
            for item in current["items"]:
                if item["id"] == ref:
                    target = item
                    break
            if target is None:
                needle = ref.casefold()
                matches = [i for i in current["items"] if i["text"].casefold() == needle]
                if not matches:
                    matches = [i for i in current["items"] if needle in i["text"].casefold()]
                if len(matches) > 1:
                    names = ", ".join(i["text"] for i in matches[:4])
                    raise TickError(f"{ref!r} matches several items: {names}")
                target = matches[0] if matches else None
            if target is None:
                raise TickError(f"no item matching {ref!r}")
            target["done"] = bool(done)
            target["done_at"] = time.time() if done else None
            current["updated_at"] = time.time()
            self.write(state)
            return {"item": target, "list": current}

    def remove(self, name: str | None, reference: str) -> dict[str, Any]:
        ref = str(reference or "").strip()
        entry = self.get_list(name)
        key = entry["id"]
        with self._locked():
            state = self.read()
            current = state["lists"][key]
            before = len(current["items"])
            current["items"] = [
                i for i in current["items"] if i["id"] != ref and i["text"].casefold() != ref.casefold()
            ]
            removed = before - len(current["items"])
            if removed == 0:
                raise TickError(f"no item matching {ref!r}")
            current["updated_at"] = time.time()
            self.write(state)
        return {"removed": removed, "list": current}

    def clear(self, name: str | None, *, done_only: bool = False) -> dict[str, Any]:
        entry = self.get_list(name)
        key = entry["id"]
        with self._locked():
            state = self.read()
            current = state["lists"][key]
            before = len(current["items"])
            current["items"] = [i for i in current["items"] if not (done_only and i["done"])] if done_only else []
            removed = before - len(current["items"])
            current["updated_at"] = time.time()
            self.write(state)
        return {"removed": removed, "list": current}

    def summary(self) -> dict[str, Any]:
        state = self.read()
        return {
            "active": state["active"],
            "lists": [
                {
                    "id": entry["id"],
                    "name": entry["name"],
                    "total": len(entry["items"]),
                    "done": sum(1 for item in entry["items"] if item["done"]),
                    "updated_at": entry["updated_at"],
                }
                for entry in state["lists"].values()
            ],
        }
