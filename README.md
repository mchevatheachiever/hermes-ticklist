# TickList

A checklist for Hermes that works in the direction that's usually missing: **you
tick, the agent is told.**

Hermes already has a `todo_list` — but only the agent writes it, and you read it.
TickList is the other way round: checkboxes in the Desktop pane, and every tick or
untick is posted into the conversation as it happens, so the model knows the fence
is actually finished without you typing it out.

- Source: https://github.com/mchevatheachiever/hermes-ticklist
- License: MIT
- Status: not in the plugin catalog yet — install from the repo (below)

## Requirements

| | |
|---|---|
| Hermes | `>=0.21.5` (declared in `plugin.yaml`) |
| Python | 3.10+ for the agent half; stdlib only, no dependencies |
| Desktop app | any. The docked-sibling-tab behaviour uses `host.openWorkspace`; older desktops are feature-detected and fall back to a plain right-docked pane |

No network calls, no credentials, no environment variables, no telemetry.

## Install

Until the catalog entry lands, install from the repository:

```bash
hermes plugins install mchevatheachiever/hermes-ticklist
```

Then enable it in **Settings ▸ Plugins**, and **restart the desktop app** (or
`Ctrl+K → "Reload desktop plugins"` after the app has reconciled). Enabling publishes
the agent half immediately, but the pane's `plugin.js` is copied into
`<hermes home>/desktop-plugins/ticklist/` by the Electron reconcile pass at app start
— so with the app already running there is no pane to show until then.

On first run the plugin drops one example list, **First ticks** — seven rows that
each demonstrate something (tick one and watch the chat, untick it, switch tabs,
delete the list). It is seeded once behind a marker file, so deleting it is final:
an empty store means you meant it, not a fresh install.

The **ticks** pane then opens in the terminal pane's zone as a sibling tab and stays
there — switch to it like any other tab. If you close it, `Ctrl+K → "TickList: show
checklist"` brings it back, on the list you were last reading.

## Use

Ask Hermes:

> make me a tick list: order brackets, book the concreters, chase the stonemason

> tick off the concreters

> what's still outstanding?

or type straight into the pane. Ticking posts `Ticked — <item>` into the chat,
which is what makes the agent see it.

## The pane

| Control | Does |
|---|---|
| **Tabs** along the top | one per list, with `done/total`; they wrap and scroll vertically past five rows, and **drag to reorder them** |
| **Checkbox** | ticks / unticks that row and posts `Ticked — <item>` into the conversation |
| **▾** | collapses the pane to a single header line showing `done/total` |
| **💬 / 🔇** | whether ticks are posted to the chat (each post is a model turn) |
| **☐ remove from list on tick** | off by default, remembered across sessions; with it on a tick deletes the row instead of striking it through |
| **✕** on a row | deletes that item |
| **Add** box | type one item per line; Enter adds |
| **⠿ grip** | drag a row **by the grip** to reorder — within its own group, written straight to the store. It's a focusable handle (`role="button"`, `tabIndex=0` — not a literal `<button>`, because Chromium refuses to start a drag from one): focus it and use **↑ / ↓** to move the row without a mouse |
| **📌 on a tab** | a pinned tab shows a pin and sits at the front of the strip |
| **📌** (header) | pins / unpins the list you're on |
| **⤓** | export menu: Text, Markdown, CSV, JSON, or copy to the clipboard |
| **Clear N ticked** | appears once something is ticked — empties the finished rows in one go, and says so in the chat |
| **Undo** | a 12-second bar after any destructive action — deleting a list, clearing ticked rows, or removing one row — restoring rows, order, ids, tick states **and timestamps** |
| **× on the active tab** | deletes that whole list — asks first, then posts `Deleted list — <name> (N items)` |
| **Tab ✕** | closes the pane; `Ctrl+K → "TickList: show checklist"` re-opens it by the same id, restoring the list you were on |

Ticked rows collect at the bottom: unticked first, ticked gathered below, order
preserved within each group — a checklist is read for what's left, but a row must
not jump out from under the cursor.

## Borrowed from Google Keep, deliberately

| Keep feature | Here |
|---|---|
| Drag to reorder | `⠿` grip on every row; drops stay inside a row's own group |
| Pin a note to the top | 📌 sorts a list to the front of the tab strip |
| "Delete checked items" | **Clear N ticked**, right under the strip |
| Undo after delete | a 12-second **Undo** bar after deleting a list, which restores the rows with their tick state |
| Search across notes | **not built** — see below |

Search is the one I left out: with the strip wrapping and scrolling, finding a list
is a click, and a search that has to say whether it matches titles or item text is a
worse answer than a pin. Add it if the tab strip ever gets past ~40 lists.

## Export

**⤓** in the header offers four file shapes and a clipboard copy:

| Format | Shape | Good for |
|---|---|---|
| Text | `[ ] item` / `[x] item`, with a done count | pasting into a message or a terminal |
| Markdown | `- [ ] item` under a heading | Obsidian, GitHub issues, Notion — anything that reads task lists |
| CSV | `done,text,created,done_at,id` | a spreadsheet, or a Todoist-style import |
| JSON | the stored list verbatim | only lossless shape — ids and timestamps survive, so a list can be restored by hand |
| Copy | the text shape, to the clipboard | a quick paste without a file on disk |

CSV cells that would be evaluated by a spreadsheet (`=`, `+`, `-`, `@`) are
prefixed with an apostrophe, so an item like `=HYPERLINK(...)` stays text.

Exports are served by `GET /lists/{name}/export?fmt=txt|md|csv|json`, which returns
`{filename, mime, content}`; the pane turns that into a download, so nothing is
written outside your Downloads folder.

## Tools

| Tool | Purpose |
|---|---|
| `tick_add` | Add items; keeps existing, skips duplicates |
| `tick_set` | Tick or untick by id or text (exact, then unique substring) |
| `tick_list` | Read a list with done/total, plus an inventory of every list (name, pinned, done/total, which is active). The other five tools return only the list they acted on |
| `tick_remove` | Delete an item |
| `tick_clear` | Empty a list, or `done_only: true` |
| `tick_delete_list` | Delete an entire list — not the same as emptying it |

Plus a bundled skill (`ticklist:ticklist`) and `/tick [list]`, which prints the list
without spending a model turn.

Text-only surfaces get a plain checklist, every line at column 0, unticked first:

```
shop — 1/3 done
██████····· 33%

[ ] brackets
[ ] paint
[x] screws
```

## How it works

- **One store, two writers.** The pane and the tools share
  `<hermes home>/plugin-data/ticklist/lists.json`, written atomically (temp file →
  `fsync` → `os.replace`) under an advisory lock, so a click and a `tick_set` are
  the same operation and cannot truncate each other.
- **Bounded input**: 240 chars per item, 200 chars per list name, 2,000 items per
  list, 50 lists, control characters stripped.
- **Ambiguity is refused, not guessed.** A substring matching two items raises and
  lists the candidates; pass the id instead.
- **Duplicate texts collapse** onto the first occurrence, case-insensitively — two
  identical rows would drift apart.
- **Item text is shown exactly as typed**, because a checklist is often pasted
  verbatim. **List titles** are the exception: a new title's first letter is
  capitalised (`vehicles` → `Vehicles`), because a tab strip of lowercase headings
  reads as a bug. All-lowercase opening words only — `DIY bits` and `iPad list` are
  left alone, and the list's key is unchanged, so lookups still work either way.

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
  `pos: 'right'` would split a new zone beside it. `enforce` replays the placement
  at boot.
- Re-opening the same id fronts the existing tab. The list you were reading is kept
  in `ctx.storage`, so a reopen lands where you left off rather than snapping to the
  backend's "active" list — which is whichever list was last written to.
- There is deliberately **no status-bar chip**: the pane is a permanent tab, so a
  chip would be a second door for something already one click away.

Names hold up to 200 characters and are never truncated in the store, because the
store key is derived from the name and a cut name stops resolving. Truncation is the
renderer's job: the tab ellipsises at 14rem, the header title at its available width.

`hermes plugins update` is as inert as `install` until the app restarts — it refreshes
the agent half and does not publish the desktop half.

Reload the desktop half with **Ctrl+K → "Reload desktop plugins"**
(`plugins.reload`, which re-scans the plugins root without a window reload). **"Reload
window"** is the heavier fallback — a full `location.reload()` — for when the pane
itself is wedged. The desktop half also hot-reloads when `plugin.js` changes. On the Python side,
commands and hook reloads land immediately, but **tool schemas only appear in the
next session** — restart the gateway only to avoid opening one.

## API

The pane polls cheap and fetches detail on demand:

| Route | Returns | Polled |
|---|---|---|
| `GET /lists` | every list as `{id, name, pinned, done, total, updated_at}` — plus the rows of the active list, so a pane that hasn't reloaded still paints | every 3s |
| `GET /lists/{name}` | one list with its rows | every 3s, for the list on screen |
| `POST /lists` | full state after the write; takes `create_empty: true` for a list with no items (undo of an empty list) | on action |
| `PATCH /lists/{name}` | full state; `{pinned: true\|false}` | on pin |
| `PATCH /order` | full state; `{ids: [...]}`, required — reorders the tab strip | on tab drop |
| `PATCH/DELETE /items/{id}`, `POST /clear` | full state after the write | on action |
| `DELETE /lists/{name}` | full state plus `{deleted: {name, items}}` | on action |
| `PATCH /lists/order` | full state, after reordering the tabs to `{ids: [...]}` | on tab drop |
| `PATCH /lists/{name}/order` | full state, after reordering to `{ids: [...]}` | on drop |
| `PATCH /lists/{name}/items` | full state, after writing rows back verbatim (`{items: [...]}`) | undo |
| `GET /lists/{name}/export?fmt=` | `{filename, mime, content}` | on export |
| `GET /health` | `{ok, lists}` — never the exception text, which carries the store path | — |

Item writes take `?list=` — the pane sends the list **id**; a display name resolves too.
Omitting it falls back to the active list, which is **not** the tab on screen, so send
it explicitly.

Tab reordering lives at `PATCH /order`, not `/lists/order`: the latter is a list *name*
as well, and the static segment shadows the name route — a list called `order` could
never be pinned.

Measured on a real 22-list / 303-item store: **19.8 KiB → 2.6 KiB per poll**. At the
documented ceiling (50 lists × 2,000 items) the old single-endpoint shape shipped
**7.6 MiB every three seconds**; the split brings it to **0.18 MiB**, with a single
list fetched on demand.

## Disclosure

- **No network calls.** Nothing leaves the machine except the tick notices you see
  in the chat.
- **Local state only**: `plugin-data/ticklist/lists.json`.
- **Pinning is not announced.** It's a view preference — it changes nothing about the
  list — and every chat post costs a model turn. The agent reads pin state from
  `tick_list` instead, which returns every list with its `pinned` flag.
- **Chat hand-off**: a tick posts `Ticked — <item>` into the active composer. The 💬
  toggle turns it off; nothing else in the plugin writes to the chat.
- **Item text is sent to your model provider.** That post is a real user turn, so
  the item name goes to whichever provider serves the session and is stored in the
  session transcript. Don't put secrets on a list with announcing on.
- **API authorisation is the host's, not the plugin's.** Routes are mounted at
  `/api/plugins/ticklist/` behind the Hermes dashboard's own access control; the
  plugin adds no auth of its own and should not be exposed beyond it.

## Known limits

- **No row virtualisation.** A 2,000-item list mounts 2,000 rows. Fine in the
  hundreds, gooey at the ceiling. Fix, if anyone actually hits it: window the list
  to the visible range, or cap the render behind a "show all" toggle.
- **`replace_items()` does not dedupe by text**, while `normalise_items()` does. The
  undo path needs verbatim rows, but a client posting two identical texts makes
  `tick_set "<text>"` ambiguous. Reachable only through the API, not the pane.
- **`/lists` still carries the active list's rows.** That is a deliberate compat
  shim for the reload window (desktop hot-reloads, API needs a gateway restart), not
  an oversight; it is one list, not the whole store.

## Development

```bash
python3 scripts/check_setters.py desktop/plugin.js   # mount-time guard
node --check desktop/plugin.js                       # the file is loaded uncompiled
cd tests && python3 -m unittest test_core test_api   # 69 core + 23 API
hermes plugins validate . --install-deps             # catalog admission
hermes plugins doctor . --ci
```

`scripts/check_setters.py` runs five checks, all for mistakes that are valid
JavaScript and pass `node --check` yet kill the pane on mount or render as nothing:
a `setFoo()` whose `useState` was deleted; a `setFoo()` declared and never called (a
control the docs promise but nothing renders); a `useX()` used but never imported
from react; an `area:` value written as a quoted constant; and a `Button`
`variant`/`size` the app doesn't define — an unknown variant compiles to no classes
at all.

Run the tests from inside `tests/`: a `PYTHONPATH` entry pointing at the Hermes
checkout shadows the name `tests`, and the module is then reported "not found".

## License

MIT — see [LICENSE](LICENSE).
