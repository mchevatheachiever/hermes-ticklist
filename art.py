"""Terminal rendering for ticklist — the text-only half.

The Desktop pane draws checkboxes; everything else gets this. Every line starts at
column 0 because models re-type tool output and leading whitespace is the first
casualty.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

def _core_module():
    """Find the core module however this file was loaded.

    Three loading paths exist: as `ticklist.export` inside the package, as a
    top-level module in tests, and by file path from `plugin_api.py` — where the
    core module is already in `sys.modules` under a different name. Guessing with
    a plain `import core` works in the first two and fails in the third, which is
    the one that runs in production.
    """
    import importlib.util
    import sys

    for name in ("ticklist_core", "core"):
        module = sys.modules.get(name)
        if module is not None and hasattr(module, "ordered_items"):
            return module

    path = Path(__file__).resolve().parent / "core.py"
    spec = importlib.util.spec_from_file_location("ticklist_core", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("ticklist_core", module)
    spec.loader.exec_module(module)
    return module

ordered_items = _core_module().ordered_items

BOX_DONE = "[x]"
BOX_TODO = "[ ]"


def render_list(entry: dict[str, Any], *, width: int = 46) -> str:
    items: Sequence[dict[str, Any]] = ordered_items(entry)
    done = sum(1 for item in items if item["done"])
    total = len(items)
    title = f"{entry.get('name', 'ticklist')} — {done}/{total} done"

    if not items:
        return f"{title}\n(empty — add items with tick_add)"

    bar_width = width - 12
    filled = 0 if total == 0 else round(bar_width * done / total)
    bar = "█" * filled + "·" * (bar_width - filled)

    lines = [title, f"{bar} {done * 100 // total if total else 0}%", ""]
    label_width = min(width - 6, max(len(str(item["text"])) for item in items))
    for item in items:
        mark = BOX_DONE if item["done"] else BOX_TODO
        text = str(item["text"])
        if len(text) > label_width:
            # An ellipsis, not a clean cut: a silently halved label reads as a
            # different item.
            text = text[: max(1, label_width - 1)] + "…"
        lines.append(f"{mark} {text}")
    return "\n".join(lines)


def render_change(item: dict[str, Any]) -> str:
    """One-line notice for a tick/untick, used when something changed underneath."""
    mark = BOX_DONE if item.get("done") else BOX_TODO
    verb = "ticked" if item.get("done") else "unticked"
    return f"{mark} {item.get('text', '')} — {verb}"
