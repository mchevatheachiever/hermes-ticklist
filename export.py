"""List exports — one shape per destination, all from the same store entry.

Text and Markdown are for humans and for pasting into other tools; CSV is for a
spreadsheet; JSON is the only lossless one (ids and timestamps survive, so it can
be re-imported).
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

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

    for name in ("ticklist_core", "ticklist.core", "core"):
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


def _cell(value: Any) -> str:
    """Neutralise spreadsheet formulas.

    Excel, Sheets and LibreOffice evaluate a cell that starts with = + - @ (or a
    tab / carriage return), so an item like `=HYPERLINK(...)` becomes live code in
    a CSV the user opens. Prefixing with an apostrophe keeps it as text.
    """
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text

FORMATS = {
    "txt": ("text/plain; charset=utf-8", "txt"),
    "md": ("text/markdown; charset=utf-8", "md"),
    "csv": ("text/csv; charset=utf-8", "csv"),
    "json": ("application/json", "json"),
}


def build_text(entry: dict[str, Any]) -> str:
    items = ordered_items(entry)
    done = sum(1 for item in items if item["done"])
    lines = [f"{entry['name']} — {done}/{len(items)} done", ""]
    lines += [f"[{'x' if item['done'] else ' '}] {item['text']}" for item in items]
    return "\n".join(lines) + "\n"


def build_markdown(entry: dict[str, Any]) -> str:
    """A task list any Markdown tool understands (Obsidian, GitHub, Notion)."""
    items = ordered_items(entry)
    done = sum(1 for item in items if item["done"])
    lines = [f"# {entry['name']}", "", f"*{done}/{len(items)} done*", ""]
    lines += [f"- [{'x' if item['done'] else ' '}] {item['text']}" for item in items]
    return "\n".join(lines) + "\n"


def build_csv(entry: dict[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["done", "text", "created", "done_at", "id"])
    for item in ordered_items(entry):
        writer.writerow(
            [
                "true" if item["done"] else "false",
                _cell(item["text"]),
                _cell(item.get("created") or ""),
                _cell(item.get("done_at") or ""),
                _cell(item["id"]),
            ]
        )
    return buffer.getvalue()


def build_json(entry: dict[str, Any]) -> str:
    return json.dumps(entry, indent=2, ensure_ascii=False) + "\n"


BUILDERS = {
    "txt": build_text,
    "md": build_markdown,
    "csv": build_csv,
    "json": build_json,
}


def build(entry: dict[str, Any], fmt: str) -> tuple[str, str, str]:
    """Returns (content, mime type, filename suffix)."""
    if fmt not in BUILDERS:
        raise ValueError(f"unknown format {fmt!r}; try one of {', '.join(FORMATS)}")
    return BUILDERS[fmt](entry), FORMATS[fmt][0], FORMATS[fmt][1]
