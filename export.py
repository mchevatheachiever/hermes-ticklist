"""List exports — one shape per destination, all from the same store entry.

Text and Markdown are for humans and for pasting into other tools; CSV is for a
spreadsheet; JSON is the only lossless one (ids and timestamps survive, so it can
be re-imported).
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

FORMATS = {
    "txt": ("text/plain; charset=utf-8", "txt"),
    "md": ("text/markdown; charset=utf-8", "md"),
    "csv": ("text/csv; charset=utf-8", "csv"),
    "json": ("application/json", "json"),
}


def build_text(entry: dict[str, Any]) -> str:
    done = sum(1 for item in entry["items"] if item["done"])
    lines = [f"{entry['name']} — {done}/{len(entry['items'])} done", ""]
    lines += [f"[{'x' if item['done'] else ' '}] {item['text']}" for item in entry["items"]]
    return "\n".join(lines) + "\n"


def build_markdown(entry: dict[str, Any]) -> str:
    """A task list any Markdown tool understands (Obsidian, GitHub, Notion)."""
    done = sum(1 for item in entry["items"] if item["done"])
    lines = [f"# {entry['name']}", "", f"*{done}/{len(entry['items'])} done*", ""]
    lines += [f"- [{'x' if item['done'] else ' '}] {item['text']}" for item in entry["items"]]
    return "\n".join(lines) + "\n"


def build_csv(entry: dict[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["done", "text", "created", "done_at", "id"])
    for item in entry["items"]:
        writer.writerow(
            [
                "true" if item["done"] else "false",
                item["text"],
                item.get("created") or "",
                item.get("done_at") or "",
                item["id"],
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
