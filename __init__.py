"""ticklist — a checklist the agent can see you tick.

Agent half: five tools. Desktop half: `desktop/plugin.js`, a pane of checkboxes
that posts each tick/untick into the conversation as it happens.

The pane opens through `host.openWorkspace`, docks beside the terminal pane, and the
tab's own Close tears it down; re-opening the same id fronts the tab again, on the
list the user was reading.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from . import art, core, schemas
from .tools import tick_add, tick_clear, tick_delete_list, tick_list, tick_remove, tick_set

logger = logging.getLogger(__name__)

_ID = "ticklist"


def _slash_tick(raw_args: str = "") -> str:
    """`/tick [list]` — print the list without spending a model turn."""
    name = (raw_args or "").strip() or None
    try:
        entry = core.TickStore().get_list(name)
    except core.TickError as exc:
        return f"ticklist: {exc}"
    except OSError as exc:
        return f"ticklist: could not read the store ({exc})"
    return art.render_list(entry)


def register(ctx: Any) -> None:
    ctx.register_tool(
        name="tick_add",
        toolset="ticklist",
        schema=schemas.ADD,
        handler=tick_add,
        description="Add items to a Desktop checklist.",
    )
    ctx.register_tool(
        name="tick_set",
        toolset="ticklist",
        schema=schemas.SET,
        handler=tick_set,
        description="Tick or untick an item on a checklist.",
    )
    ctx.register_tool(
        name="tick_list",
        toolset="ticklist",
        schema=schemas.LIST,
        handler=tick_list,
        description="Read a checklist with its done/total state.",
    )
    ctx.register_tool(
        name="tick_remove",
        toolset="ticklist",
        schema=schemas.REMOVE,
        handler=tick_remove,
        description="Delete an item from a checklist.",
    )
    ctx.register_tool(
        name="tick_clear",
        toolset="ticklist",
        schema=schemas.CLEAR,
        handler=tick_clear,
        description="Empty a checklist, or just its finished items.",
    )

    ctx.register_tool(
        name="tick_delete_list",
        toolset="ticklist",
        schema=schemas.DELETE_LIST,
        handler=tick_delete_list,
        description="Delete a whole checklist and everything on it.",
    )

    skill_file = Path(__file__).resolve().parent / "skills" / _ID / "SKILL.md"
    if skill_file.exists():
        try:
            ctx.register_skill(_ID, skill_file)
        except Exception as exc:  # pragma: no cover - older Hermes
            logger.debug("ticklist: skill registration skipped: %s", exc)

    ctx.register_command(
        "tick",
        _slash_tick,
        description="Print a checklist in the transcript",
        args_hint="[list name]",
    )

    try:
        core.ensure_seed()
    except (core.TickError, OSError) as exc:  # pragma: no cover - never block loading
        logger.debug("ticklist: seed skipped: %s", exc)

    logger.debug("ticklist: registered 6 tools")
