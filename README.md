# TickList

A checklist for Hermes that works in the direction that's usually missing: **you
tick, the agent is told.**

Hermes already has a `todo_list` — but only the agent writes it, and you read it.
TickList is the other way round: checkboxes in the Desktop pane, and every tick
or untick is posted into the conversation as it happens, so the model knows the
fence is actually finished without you typing it out.

## Install

```bash
hermes plugins install ticklist
```

Enable it in **Settings ▸ Plugins**, then open the **ticks** pane. `⌘K →
TickList: show / hide checklist` toggles the pane at any time — closing it does
not mean hunting through Settings to get it back.

## Use

Ask Hermes:

> make me a tick list: order brackets, book the concreters, chase the stonemason

> tick off the concreters

> what's still outstanding?

or type straight into the pane. Ticking posts `Ticked — <item>` into the chat,
which is what makes the agent see it.

## Closing, collapsing

- **✕** in the pane header closes it. Reopen from ⌘K — the pane is unregistered
  and re-registered through the disposer `ctx.register` returns, so no trip to
  Settings.
- **▾** collapses it to a single header line showing `done/total`.
- **💬** decides whether ticks are posted to the chat (each post is a model turn).

## Tools

| Tool | Purpose |
|---|---|
| `tick_add` | Add items; keeps existing, skips duplicates |
| `tick_set` | Tick or untick by id or text (exact, then unique substring) |
| `tick_list` | Read a list with done/total |
| `tick_remove` | Delete an item |
| `tick_clear` | Empty a list, or `done_only: true` |

Plus a bundled skill (`ticklist:ticklist`) and `/tick [list]`, which prints the
list without spending a model turn.

Text-only surfaces get a plain checklist, every line at column 0:

```
shop — 1/3 done
██████····· 33%

[x] screws
[ ] brackets
[ ] paint
```

## How it works

- **One store, two writers.** The pane and the tools share
  `<hermes home>/plugin-data/ticklist/lists.json`, written atomically under an
  advisory lock, so a click and a `tick_set` are the same operation.
- **Ambiguity is refused, not guessed.** A substring matching two items raises
  and lists the candidates; pass the id instead.
- **Duplicate texts collapse** onto the first occurrence, case-insensitively —
  two identical rows would drift apart.
- **Uppercase is a display choice** on the wheel's side; here the item text is
  shown exactly as typed, because a checklist is often pasted verbatim.

## Disclosure

- **No network calls.** Nothing leaves the machine except the tick notices you
  see in the chat.
- **Local state only**: `plugin-data/ticklist/lists.json` (max 2,000 items per
  list, 50 lists).
- **No credentials**, no environment variables, no telemetry.
- **Chat hand-off**: a tick posts `Ticked — <item>` into the active composer.
  The 💬 toggle turns it off; nothing else in the plugin writes to the chat.

## Development

```bash
python3 scripts/check_setters.py desktop/plugin.js   # dead-useState guard
node --check desktop/plugin.js
python3 -m unittest tests.test_core                  # core + art, stdlib only
hermes plugins validate . --install-deps             # catalog admission gate
```

API tests need FastAPI (the Hermes runtime venv has it):

```bash
"$HERMES_VENV/bin/python" -m unittest tests.test_api
```

## License

MIT
