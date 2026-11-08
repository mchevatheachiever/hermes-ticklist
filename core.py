"""TickList core — the checklist store, shared by the tools and the API half.

One list per name (default ``ticklist``), items are ``{id, text, done, created,
done_at}``. State lives in ``<hermes home>/plugin-data/ticklist/lists.json`` and
is written atomically under an advisory lock, so the pane and the agent can both
write without truncating each other.

No network, no credentials, stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import tempfile
import time
from collections.abc import Mapping
from contextlib import contextmanager
from typing import Any, Iterable, Iterator

try:  # POSIX advisory locking; degrades to no lock on Windows.
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

SCHEMA_VERSION = 1
MAX_ITEMS = 2000
MAX_TEXT_CHARS = 240
MAX_NAME_CHARS = 200
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
    text = _CTRL_RE.sub(" ", raw).strip() or default
    # A list title is a heading, so it starts with a capital: models create
    # lowercase names ("vehicles"), and a tab strip of lowercase labels reads
    # like a bug. Only an all-lowercase opening word is touched, so acronyms and
    # camelCase names the user typed ("DIY", "iPad") survive.
    if text[:1].islower() and (len(text) == 1 or not text[1:2].isupper()):
        text = text[0].upper() + text[1:]
    if len(text) > MAX_NAME_CHARS:
        # Refuse rather than truncate. The store key is derived from the raw
        # name and every later lookup goes through it, so a truncated *display*
        # name silently stops resolving — the list stays visible but inert.
        # Truncating for the screen is the renderer's job, not the store's.
        raise TickError(f"a list name holds at most {MAX_NAME_CHARS} characters")
    return text


def slugify(name: str) -> str:
    """Stable key for a list name.

    Truncation keeps a short hash of the *whole* slug: two long names that share
    their first 48 characters would otherwise collide and silently merge into one
    list, with the second one's items landing inside the first.
    """
    raw = _SLUG_RE.sub("-", str(name).strip().lower()).strip("-")
    if not raw:
        return "ticklist"
    if len(raw) > 48:
        return raw[:39] + "-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    return raw


def _as_float(value: Any, default: float | None = None) -> float | None:
    """Coerce a timestamp from disk without ever raising.

    A hand-edited or half-written store must not turn every route into a 500; a
    bad timestamp is cosmetic, a crash is not.
    """
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def ordered_items(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Unticked rows first, ticked collected at the bottom, stable inside a group.

    The single implementation: the pane, the text art and the exports all need
    this order, and three copies would drift.
    """
    items = list(entry.get("items") or [])
    items.sort(key=lambda item: bool(item.get("done")))
    return items


def list_key(raw: Any) -> str:
    """Stable store key for a list name, derived from the name BEFORE truncation.

    ``clean_name`` cuts the display text to 60 characters (and says so with an
    ellipsis), so slugifying the *display* name would erase the very tail that
    distinguishes two long names — they would hash identically and merge.
    """
    if raw is None:
        return slugify("ticklist")
    if not isinstance(raw, str):
        raise TickError("list name must be text")
    return slugify(_CTRL_RE.sub(" ", raw).strip() or "ticklist")


def new_id() -> str:
    return secrets.token_hex(4)


def normalise_items(raw: Any) -> list[dict[str, Any]]:
    """Accept ``["a", "b"]`` or ``[{"text": "a", "done": true}]``.

    Duplicate texts collapse onto the first occurrence (case-insensitive): two
    identical rows are indistinguishable on screen and would drift apart.
    """
    if isinstance(raw, Mapping):
        raise TickError(
            "items must be a list of texts — wrap a single item in a list, e.g. [\"milk\"]"
        )
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


def ordered_entries(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Pinned lists first, user order preserved inside each group.

    `sorted` is stable, so this never reshuffles the tabs the user arranged.
    """
    entries = list(state["lists"].values())
    entries.sort(key=lambda entry: not entry.get("pinned"))
    return entries


def _empty_state() -> dict[str, Any]:
    return {"version": SCHEMA_VERSION, "active": "", "lists": {}}


SEED_LIST = "First ticks"
SEED_ITEMS: list[dict[str, Any]] = [
    {"text": "Tick this one — the agent hears about it in the chat", "done": False},
    {"text": "Untick it again: nothing here is permanent", "done": False},
    {"text": "Add something only you would put on a list", "done": False},
    {"text": "Click another tab — every list is one click away", "done": False},
    {"text": "Delete this list when you're bored; the plugin won't sulk", "done": False},
    {"done": True, "text": "Ticked rows collect down the bottom, out of the way"},
    {"done": True, "text": "And a tick costs one model turn — see the 💬 toggle"},
]


def ensure_seed(store: "TickStore | None" = None) -> str:
    """Drop the example list in once, on a store that has never been touched.

    A marker file rather than an emptiness check: an empty store means "the user
    deleted everything", which is a decision to respect, not a fresh install.
    Returns the list name when it seeded, "" otherwise.
    """
    store = store if store is not None else TickStore()
    marker = store.root / ".seeded"
    if marker.exists():
        return ""
    store.root.mkdir(parents=True, exist_ok=True)
    seeded = ""
    if not store.summary()["lists"]:
        store.add_items(SEED_LIST, SEED_ITEMS)
        seeded = SEED_LIST
    try:
        marker.write_text(str(int(time.time())), encoding="utf-8")
    except OSError:  # pragma: no cover - read-only volume
        pass
    return seeded


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
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return _empty_state()
        try:
            raw = json.loads(text)
        except (json.JSONDecodeError, ValueError, TypeError):
            # Quarantine before returning an empty state: the very next write
            # would otherwise replace the user's items with a fresh empty file,
            # turning one corrupt byte into a total, silent wipe.
            self._quarantine()
            return _empty_state()
        if not isinstance(raw, dict):
            return _empty_state()
        state = _empty_state()
        state["active"] = str(raw.get("active") or "")
        lists = raw.get("lists")
        if isinstance(lists, dict):
            for key, entry in lists.items():
                try:
                    clean = self._clean_list(key, entry)
                except (ValueError, TypeError, AttributeError):
                    # One unreadable list must not take the whole store with it.
                    continue
                if clean is not None:
                    state["lists"][key] = clean
        if state["active"] not in state["lists"]:
            state["active"] = next(iter(state["lists"]), "")
        return state

    def _quarantine(self) -> None:
        """Move an unparseable store aside so it survives the next write."""
        target = self.root / f"lists.json.corrupt-{int(time.time())}"
        try:
            os.replace(self.path, target)
        except OSError:  # pragma: no cover - read-only volume
            pass

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
                    "created": _as_float(item.get("created")) or time.time(),
                    "done_at": _as_float(item.get("done_at")),
                }
            )
        return {
            "id": key,
            "name": clean_name(entry.get("name"), default=key),
            "items": items[:MAX_ITEMS],
            "pinned": bool(entry.get("pinned")),
            "created_at": _as_float(entry.get("created_at")) or time.time(),
            "updated_at": _as_float(entry.get("updated_at")) or time.time(),
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
        if name is None:
            key = state["active"]
            entry = lists.get(key)
        else:
            key = list_key(name)
            entry = lists.get(key)
            if entry is None:
                # Fallback for entries written before names stopped being
                # truncated: match on the display name the caller can actually
                # read, rather than failing on the key they never saw.
                wanted = str(name).strip().casefold()
                entry = next(
                    (e for e in lists.values() if e["name"].casefold() == wanted), None
                )
                if entry is not None:
                    key = entry["id"]
        if entry is None:
            known = ", ".join(sorted(entry["name"] for entry in lists.values()))
            raise TickError(f"no list called {name!r}; known lists: {known}")
        return entry

    def ensure_list(self, name: str | None = None) -> dict[str, Any]:
        display = clean_name(name)
        key = list_key(name)
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
                    "pinned": False,
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

    def replace_items(self, name: str | None, rows: Any) -> dict[str, Any]:
        """Write the row array back verbatim — the restore half of undo.

        Ids, order, tick states and timestamps are all preserved when the caller
        supplies them, so an undo puts the list back exactly as it was rather
        than as a set of lookalikes at the end of the list.
        """
        if isinstance(rows, Mapping):
            raise TickError("items must be a list of rows")
        if not isinstance(rows, Iterable) or isinstance(rows, str):
            raise TickError("items must be a list of rows")
        rebuilt: list[dict[str, Any]] = []
        now = time.time()
        for row in rows:
            if isinstance(row, Mapping):
                text = clean_text(row.get("text"))
                item = {
                    "id": str(row.get("id") or new_id())[:16],
                    "text": text,
                    "done": bool(row.get("done")),
                    "created": _as_float(row.get("created")) or now,
                    "done_at": _as_float(row.get("done_at")),
                }
            else:
                item = {
                    "id": new_id(),
                    "text": clean_text(row),
                    "done": False,
                    "created": now,
                    "done_at": None,
                }
            rebuilt.append(item)
            if len(rebuilt) > MAX_ITEMS:
                raise TickError(f"a list holds at most {MAX_ITEMS} items")
        seen_ids: set[str] = set()
        for item in rebuilt:
            if item["id"] in seen_ids:
                # Two rows sharing an id make the order unfixable: reorder's
                # id->row map collapses and can never match the row count again.
                raise TickError(f"duplicate row id {item['id']!r}")
            seen_ids.add(item["id"])
        entry = self.get_list(name)
        key = entry["id"]
        with self._locked():
            state = self.read()
            current = state["lists"][key]
            current["items"] = rebuilt
            current["updated_at"] = now
            self.write(state)
        return {"list": current}

    def set_pinned(self, name: str | None, pinned: bool) -> dict[str, Any]:
        entry = self.get_list(name)
        key = entry["id"]
        with self._locked():
            state = self.read()
            current = state["lists"][key]
            current["pinned"] = bool(pinned)
            current["updated_at"] = time.time()
            self.write(state)
        return {"list": current}

    def reorder(self, name: str | None, ids: Iterable[Any]) -> dict[str, Any]:
        """Set the item order. The caller must name every item exactly once.

        A partial list is refused rather than merged: a dropped row would vanish
        from the user's order and reappear at the end on the next load.
        """
        entry = self.get_list(name)
        key = entry["id"]
        wanted = [str(item) for item in ids]
        with self._locked():
            state = self.read()
            current = state["lists"][key]
            by_id = {item["id"]: item for item in current["items"]}
            if len(wanted) != len(by_id) or set(wanted) != set(by_id):
                raise TickError("the new order must list every item on the list exactly once")
            current["items"] = [by_id[item_id] for item_id in wanted]
            current["updated_at"] = time.time()
            self.write(state)
        return {"list": current}

    def delete_list(self, name: str | None) -> dict[str, Any]:
        """Remove a list and everything on it. Returns what was lost."""
        entry = self.get_list(name)
        key = entry["id"]
        with self._locked():
            state = self.read()
            removed = state["lists"].pop(key, None)
            if removed is None:
                raise TickError(f"no list called {name!r}")
            if state["active"] == key:
                state["active"] = next(iter(state["lists"]), "")
            self.write(state)
        return {"id": key, "name": removed["name"], "items": len(removed["items"])}

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
        entries = ordered_entries(state)
        return {
            "active": state["active"],
            "lists": [
                {
                    "id": entry["id"],
                    "name": entry["name"],
                    "total": len(entry["items"]),
                    "done": sum(1 for item in entry["items"] if item["done"]),
                    "pinned": bool(entry.get("pinned")),
                    "updated_at": entry["updated_at"],
                }
                for entry in entries
            ],
        }
