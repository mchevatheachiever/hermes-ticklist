---
name: ticklist
description: "Tick-list items in the Desktop pane; every tick reaches the agent."
version: 1.1.1
---

# TickList

A checklist the user ticks in the Hermes Desktop pane. The point of the plugin is
the direction of travel: **the person ticks, and the agent is told.** Core's
`todo_list` is the other way round — agent-authored, user-read.

## When to use it

- The user gives you a list of things to do, buy, pack, book or check.
- The user says something is done ("I've done the fence", "got the brackets") —
  find the item and tick it rather than editing a list in prose.
- Something needs tracking across turns and the user will be clicking on it.

Do **not** use it as scratch memory for your own multi-step work — that is what
`todo_list` is for, and its state rides through context compression.

## Tools

| Tool | Use |
|---|---|
| `tick_add` | Add items (strings). Existing items are kept, duplicates skipped. |
| `tick_set` | Tick/untick by id or by text. Exact match first, then a unique substring. |
| `tick_list` | Read a list with done/total counts. |
| `tick_remove` | Delete an item (not the same as unticking). |
| `tick_clear` | Empty a list, or `done_only: true` to clear the finished ones. |

Every tool returns a `display` field — a text checklist. Copy it into your reply
exactly, in one fenced code block, so the list is visible in CLI, TUI and Discord.
Every line already starts at column 0; do not re-indent it.

## Ambiguity

A substring that matches two items is refused, not guessed. When that happens ask
which one, or pass the item id (ids come back in `tick_list`).

## The pane

Checkboxes, an add box, a scrolling strip of per-list tabs with `done/total`, a 💬
toggle that decides whether a tick is posted into the chat, a chevron that collapses
the pane to its header, and a checkbox for **remove from list on tick** (off by
default, remembered). The pane lives as a tab beside TERMINAL; if it is closed,
`Ctrl+K → "TickList: show checklist"` reopens it on the list the user was reading.

Unticked rows sit above ticked ones in both the pane and the text checklist.

Ticking posts `Ticked — <item>` (or `Unticked — …`) into the conversation, which
starts a turn: that is how you see it. It also means each tick costs a model
call, so do not ask the user to tick fifty things in a row.

## Pitfalls

- Duplicate texts collapse onto the first occurrence, case-insensitively.
- Unticking clears `done_at`; don't report a stale completion time.
- A list with no items is legal; `tick_set` on it raises.
