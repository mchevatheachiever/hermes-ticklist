"""TickList backend routes — mounted at /api/plugins/ticklist/.

The pane and the agent tools share one store, so a tick in the UI and a
`tick_set` call are the same write.

No ``from __future__ import annotations``: pydantic resolves model annotations at
class creation, and stringised ones break when this module is imported by path.
"""

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def _load(module_name: str, filename: str) -> Any:
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, PLUGIN_ROOT / filename)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


core = _load("ticklist_core", "core.py")
export = _load("ticklist_export", "export.py")
router = APIRouter()
logger = logging.getLogger(__name__)


class AddPayload(BaseModel):
    items: Any = Field(default_factory=list)
    # Undo of a deleted *empty* list has nothing to re-add, so the create has to
    # be possible without items.
    create_empty: bool = False
    list: str | None = Field(default=None, max_length=200)


class DonePayload(BaseModel):
    done: bool = True


class ItemsPayload(BaseModel):
    items: Any = Field(default_factory=list)


class ListOrderPayload(BaseModel):
    # Required: a stray PATCH body must 422 rather than silently writing [] and
    # resetting the user's tab order to creation order.
    ids: list[str]


class PinPayload(BaseModel):
    pinned: bool = True


class OrderPayload(BaseModel):
    ids: list[str] = Field(default_factory=list)


class ClearPayload(BaseModel):
    done_only: bool = False


def _items(entry: dict[str, Any]) -> list[dict[str, Any]]:
    # created/done_at travel with the row so an undo can restore them; without
    # them the snapshot loses the timestamps and the CSV columns change.
    return [
        {
            "id": item["id"],
            "text": item["text"],
            "done": item["done"],
            "created": item.get("created"),
            "done_at": item.get("done_at"),
        }
        for item in entry["items"]
    ]


def _summary(entry: dict[str, Any]) -> dict[str, Any]:
    """Everything the tab strip needs and nothing it doesn't — no item rows."""
    return {
        "id": entry["id"],
        "name": entry["name"],
        "pinned": bool(entry.get("pinned")),
        "updated_at": entry["updated_at"],
        "done": sum(1 for item in entry["items"] if item["done"]),
        "total": len(entry["items"]),
    }


def _view(entry: dict[str, Any]) -> dict[str, Any]:
    return {**_summary(entry), "items": _items(entry)}


def _state() -> dict[str, Any]:
    """One read of the store for the whole payload.

    ``get_list`` re-reads and re-parses ``lists.json`` on every call, so looping
    it over the summary made each poll O(lists^2) file reads — 50 lists meant 50
    parses per request, every 3 seconds.
    """
    state = core.TickStore().read()
    active = state["active"]
    lists = []
    for entry in core.ordered_entries(state):
        view = _summary(entry)
        if entry["id"] == active:
            # The active list keeps its rows: a pane that has not reloaded yet
            # still renders, and the first paint has something to draw.
            view["items"] = _items(entry)
        lists.append(view)
    return {"ok": True, "active": active, "lists": lists}


@router.get("/lists")
async def get_lists() -> dict[str, Any]:
    try:
        return _state()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"store unreadable: {exc}") from exc


@router.patch("/lists/{name}/items")
async def replace_items(name: str, payload: ItemsPayload) -> dict[str, Any]:
    """Restore a list's rows verbatim — undo, from the pane."""
    try:
        core.TickStore().replace_items(name, payload.items)
    except core.TickError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"store unwritable: {exc}") from exc
    return _state()


@router.patch("/order")
async def set_list_order(payload: ListOrderPayload) -> dict[str, Any]:
    """Reorder the tab strip.

    Deliberately NOT `/lists/order`: that path is a list *name* too, and the
    static segment shadows it — a list called "order" could never be pinned
    (`PATCH /lists/order` hit this route, resetting the tab order instead).
    """
    try:
        core.TickStore().set_list_order(payload.ids)
    except core.TickError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"store unwritable: {exc}") from exc
    return _state()


@router.patch("/lists/{name}")
async def set_pinned(name: str, payload: PinPayload) -> dict[str, Any]:
    try:
        core.TickStore().set_pinned(name, payload.pinned)
    except core.TickError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"store unwritable: {exc}") from exc
    return _state()


@router.patch("/lists/{name}/order")
async def reorder(name: str, payload: OrderPayload) -> dict[str, Any]:
    try:
        core.TickStore().reorder(name, payload.ids)
    except core.TickError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"store unwritable: {exc}") from exc
    return _state()


@router.get("/lists/{name}/export")
async def export_list(name: str, fmt: str = "txt") -> dict[str, Any]:
    try:
        entry = core.TickStore().get_list(name)
    except core.TickError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        content, mime, suffix = export.build(entry, fmt)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    safe = core.slugify(entry["name"]) or "ticklist"
    return {"ok": True, "filename": f"{safe}.{suffix}", "mime": mime, "content": content}


@router.get("/lists/{name}")
async def get_list(name: str) -> dict[str, Any]:
    """One list with its rows — what the pane fetches on a tab switch."""
    try:
        entry = core.TickStore().get_list(name)
    except core.TickError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"store unreadable: {exc}") from exc
    return {"ok": True, "list": _view(entry)}


@router.delete("/lists/{name}")
async def delete_list(name: str) -> dict[str, Any]:
    try:
        deleted = core.TickStore().delete_list(name)
    except core.TickError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"store unwritable: {exc}") from exc
    return {**_state(), "deleted": deleted}


@router.post("/lists")
async def add_items(payload: AddPayload) -> dict[str, Any]:
    try:
        if payload.create_empty:
            core.TickStore().ensure_list(payload.list)
        else:
            core.TickStore().add_items(payload.list, payload.items)
    except core.TickError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"store unwritable: {exc}") from exc
    return _state()


@router.patch("/items/{item_id}")
async def set_done(item_id: str, payload: DonePayload, list: str | None = None) -> dict[str, Any]:
    if not item_id.strip():
        # A blank id is the caller's mistake, not a missing row: 400, matching
        # the POST routes rather than reporting it as 404.
        raise HTTPException(status_code=400, detail="an item id or text is required")
    try:
        core.TickStore().set_done(list, item_id, payload.done)
    except core.TickError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"store unwritable: {exc}") from exc
    return _state()


@router.delete("/items/{item_id}")
async def remove_item(item_id: str, list: str | None = None) -> dict[str, Any]:
    if not item_id.strip():
        raise HTTPException(status_code=400, detail="an item id or text is required")
    try:
        core.TickStore().remove(list, item_id)
    except core.TickError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"store unwritable: {exc}") from exc
    return _state()


@router.post("/clear")
async def clear_list(payload: ClearPayload, list: str | None = None) -> dict[str, Any]:
    try:
        core.TickStore().clear(list, done_only=payload.done_only)
    except core.TickError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"store unwritable: {exc}") from exc
    return _state()


@router.get("/health")
async def health() -> dict[str, Any]:
    try:
        state = core.TickStore().read()
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        # Never echo the exception: it carries the store's absolute path, and
        # /health is reachable by anything that can reach the dashboard.
        logger.warning("ticklist: health check failed: %s", exc)
        return {"ok": False, "error": "store unreadable"}
    return {"ok": True, "lists": len(state["lists"])}
