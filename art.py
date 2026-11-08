"""Terminal rendering for ticklist — the text-only half.

Same asymmetry as the wheel: the Desktop pane draws checkboxes, everything else
gets this. Every line starts at column 0 because models re-type tool output and
leading whitespace is the first casualty.
"""

from __future__ import annotations

from typing import Any, Sequence

BOX_DONE = "[x]"
BOX_TODO = "[ ]"


def render_list(entry: dict[str, Any], *, width: int = 46) -> str:
    items: Sequence[dict[str, Any]] = entry.get("items") or []
    done = sum(1 for item in items if item["done"])
    total = len(items)
    title = f"{entry.get('name', 'ticklist')} — {done}/{total} done"

    if not items:
        return f"{title}\n(empty — add items with tick_add)"

    bar_width = width - 12
    filled = 0 if total == 0 else round(bar_width * done / total)
    bar = "█" * filled + "·" * (bar_width - filled)

    lines = [title, f"{bar} {done * 100 // total if total else 0}%", ""]
    label_width = min(34, max(len(str(item["text"])) for item in items))
    for item in items:
        mark = BOX_DONE if item["done"] else BOX_TODO
        text = str(item["text"])[:label_width]
        if item["done"]:
            text = f"{text}"
        lines.append(f"{mark} {text}")
    return "\n".join(lines)


def render_change(item: dict[str, Any]) -> str:
    """One-line notice for a tick/untick, used when something changed underneath."""
    mark = BOX_DONE if item.get("done") else BOX_TODO
    verb = "ticked" if item.get("done") else "unticked"
    return f"{mark} {item.get('text', '')} — {verb}"
