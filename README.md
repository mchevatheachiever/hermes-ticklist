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

Enable it in **Settings ▸ Plugins**. The **ticks** pane opens in the terminal
pane's zone, and a **`☑ done/total` chip** stays in the status bar: click it to
open the pane, close the tab when you don't want it, click the chip to bring it
back. No typing, no trip to Settings.

## Use

Ask Hermes:

> make me a tick list: order brackets, book the concreters, chase the stonemason

> tick off the concreters

> what's still outstanding?

or type straight into the pane. Ticking posts `Ticked — <item>` into the chat,
which is what makes the agent see it.

## Closing, collapsing

- **Tab ✕** closes the pane; the **status-bar chip** re-opens it by the same id.
- **▾** collapses it to a single header line showing `done/total`.
- **💬** decides whether ticks are posted to the chat (each post is a model turn).
- **☐ remove from list on tick** — off by default, remembered across sessions;
  with it on, a tick deletes the row instead of leaving it struck through.

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
- **Item text is sent to your model provider.** That post is a real user turn, so
  the item name goes to whichever provider serves the session and is stored in the
  session transcript. Don't put secrets on a list with announcing on.
- **API authorisation is the host's, not the plugin's.** Routes are mounted at
  `/api/plugins/ticklist/` behind the Hermes dashboard's own access control; the
  plugin adds no auth of its own and should not be exposed beyond it.

## API

The pane polls cheap and fetches detail on demand:

| Route | Returns | Polled |
|---|---|---|
| `GET /lists` | every list as `{id, name, done, total}` — plus the rows of the active list, so a pane that hasn't reloaded still paints | every 3s |
| `GET /lists/{name}` | one list with its rows | every 3s, for the list on screen |
| `POST /lists`, `PATCH/DELETE /items/{id}`, `POST /clear` | full state after the write | on action |
| `GET /health` | `{ok, lists}` — never the exception text, which carries the store path | — |

Measured on a real 22-list / 303-item store: **19.8 KiB → 2.6 KiB per poll**. At the
documented ceiling (50 lists × 2,000 items) the old shape shipped **7.6 MiB every
three seconds**; the split brings it to **0.18 MiB**, with a single list fetched on
demand.

## Known limits

- **No row virtualisation.** A 2,000-item list mounts 2,000 rows. Fine in the
  hundreds, gooey at the ceiling. Fix (if anyone actually hits it): window the
  list to the visible range, or cap the render with a "show all" toggle.
- **`requires_hermes: >=0.21.5`, but the chip needs a desktop with
  `host.openWorkspace`.** Older desktops are feature-detected and fall back to a
  plain right-docked pane — everything still works, the status-bar chip just isn't
  there, and the pane returns from the zone tab strip instead.

## Development

```bash
python3 scripts/check_setters.py desktop/plugin.js   # dead-useState guard
node --check desktop/plugin.js
python3 -m unittest tests.test_core                  # core + art, stdlib only
hermes plugins validate . --install-deps             # catalog admission gate
```

API tests need FastAPI (the Hermes runtime venv has it). Run them from inside
`tests/` — a `PYTHONPATH` entry for the Hermes checkout shadows the name `tests`
with its own directory and the module is then "not found":

```bash
cd tests && "$HERMES_VENV/bin/python" -m unittest test_api
```

## License

MIT

## Desktop pane

The pane docks into the **terminal pane's zone** as a sibling tab, and opens as a
closeable workspace tile:

```js
host.openWorkspace('ticklist', {
  title: 'ticks',
  dock: { pane: 'terminal', pos: 'center', enforce: true },
  minWidth: '20rem',
  render: () => jsx(TickPane, { ctx })
})
```

- `pos: 'center'` stacks into the anchor's group (a tab beside TERMINAL);
  `pos: 'right'` would split a new zone beside it. `enforce` replays it at boot.
- Re-opening the same id fronts the existing tab, so the **status-bar chip**
  (`☑ 4/48`, `area: 'statusBar.right'`) is the always-visible door: click to open,
  the tab's ✕ to close. No typing, no Settings.
- List selection lives in a scrollable tab strip along the top, one tab per list
  with `done/total`.

Reload plugins with **Ctrl+K → "Reload window"** (there is no "Reload desktop
plugins" command).
