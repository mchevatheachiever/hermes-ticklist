"""Tool handlers for ticklist. JSON strings out, never a raise."""

from __future__ import annotations

from typing import Any

from tools.registry import tool_error, tool_result

from . import art, core


def _store() -> core.TickStore:
    return core.TickStore()


def _payload(entry: dict[str, Any], **extra: Any) -> dict[str, Any]:
    done = sum(1 for item in entry["items"] if item["done"])
    return {
        "success": True,
        "list": entry["name"],
        "total": len(entry["items"]),
        "done": done,
        "items": [
            {"id": item["id"], "text": item["text"], "done": item["done"]} for item in entry["items"]
        ],
        "display": art.render_list(entry),
        **extra,
    }


def tick_add(args: dict, **kwargs: Any) -> str:
    del kwargs
    try:
        result = _store().add_items(args.get("list"), args.get("items"))
    except core.TickError as exc:
        return tool_error(str(exc))
    except OSError as exc:
        return tool_error(f"could not write the list: {exc}")

    entry = result["list"]
    added = [item["text"] for item in result["added"]]
    raw = args.get("items")
    if isinstance(raw, str):
        requested = len([line for line in raw.splitlines() if line.strip()])
    elif isinstance(raw, (list, tuple)):
        requested = len(raw)
    else:
        requested = 0
    return tool_result(_payload(entry, added=added, skipped=max(0, requested - len(added))))


def tick_set(args: dict, **kwargs: Any) -> str:
    del kwargs
    reference = args.get("item")
    if not reference:
        return tool_error("item is required")
    done = bool(args.get("done"))
    try:
        result = _store().set_done(args.get("list"), str(reference), done)
    except core.TickError as exc:
        return tool_error(str(exc))
    except OSError as exc:
        return tool_error(f"could not write the list: {exc}")
    return tool_result(_payload(result["list"], changed=art.render_change(result["item"])))


def tick_list(args: dict, **kwargs: Any) -> str:
    del kwargs
    try:
        entry = _store().get_list(args.get("list"))
    except core.TickError as exc:
        return tool_error(str(exc))
    except OSError as exc:
        return tool_error(f"could not read the list: {exc}")
    return tool_result(_payload(entry))


def tick_remove(args: dict, **kwargs: Any) -> str:
    del kwargs
    reference = args.get("item")
    if not reference:
        return tool_error("item is required")
    try:
        result = _store().remove(args.get("list"), str(reference))
    except core.TickError as exc:
        return tool_error(str(exc))
    except OSError as exc:
        return tool_error(f"could not write the list: {exc}")
    return tool_result(_payload(result["list"], removed=result["removed"]))


def tick_clear(args: dict, **kwargs: Any) -> str:
    del kwargs
    done_only = bool(args.get("done_only"))
    try:
        result = _store().clear(args.get("list"), done_only=done_only)
    except core.TickError as exc:
        return tool_error(str(exc))
    except OSError as exc:
        return tool_error(f"could not write the list: {exc}")
    return tool_result(_payload(result["list"], removed=result["removed"]))
