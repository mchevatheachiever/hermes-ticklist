"""TickList backend routes — mounted at /api/plugins/ticklist/.

The pane and the agent tools share one store, so a tick in the UI and a
`tick_set` call are the same write.

No ``from __future__ import annotations``: pydantic resolves model annotations at
class creation, and stringised ones break when this module is imported by path.
"""

import importlib.util
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def _load_core() -> Any:
    existing = sys.modules.get("ticklist_core")
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location("ticklist_core", PLUGIN_ROOT / "core.py")
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError("cannot load ticklist core")
    module = importlib.util.module_from_spec(spec)
    sys.modules["ticklist_core"] = module
    spec.loader.exec_module(module)
    return module


core = _load_core()
router = APIRouter()


class AddPayload(BaseModel):
    items: Any = Field(default_factory=list)
    list: str | None = Field(default=None, max_length=60)


class DonePayload(BaseModel):
    done: bool = True


class ClearPayload(BaseModel):
    done_only: bool = False


def _entry(list_name: str | None) -> dict[str, Any]:
    return core.TickStore().get_list(list_name)


def _view(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry["id"],
        "name": entry["name"],
        "updated_at": entry["updated_at"],
        "items": [
            {"id": item["id"], "text": item["text"], "done": item["done"]} for item in entry["items"]
        ],
        "done": sum(1 for item in entry["items"] if item["done"]),
        "total": len(entry["items"]),
    }


def _state() -> dict[str, Any]:
    store = core.TickStore()
    summary = store.summary()
    lists = []
    for meta in summary["lists"]:
        try:
            lists.append(_view(store.get_list(meta["id"])))
        except core.TickError:  # pragma: no cover - raced removal
            continue
    return {"ok": True, "active": summary["active"], "lists": lists}


@router.get("/lists")
async def get_lists() -> dict[str, Any]:
    try:
        return _state()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"store unreadable: {exc}") from exc


@router.post("/lists")
async def add_items(payload: AddPayload) -> dict[str, Any]:
    try:
        core.TickStore().add_items(payload.list, payload.items)
    except core.TickError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"store unwritable: {exc}") from exc
    return _state()


@router.patch("/items/{item_id}")
async def set_done(item_id: str, payload: DonePayload, list: str | None = None) -> dict[str, Any]:
    try:
        core.TickStore().set_done(list, item_id, payload.done)
    except core.TickError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"store unwritable: {exc}") from exc
    return _state()


@router.delete("/items/{item_id}")
async def remove_item(item_id: str, list: str | None = None) -> dict[str, Any]:
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
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "lists": len(state["lists"])}
