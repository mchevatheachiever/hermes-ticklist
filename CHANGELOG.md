# Changelog

All notable changes to this plugin. Versions follow the `plugin.yaml` version.

## 1.8.2 — 2026-11-08

### Fixed
- **The upgrade instruction named the wrong service.** The pane is served by the dashboard
  process (`hermes-serve*.service` on a systemd install), not the messaging gateway — so
  following the README after an update would not have cleared the 404 it was meant to fix.
  Wording is now generic, with `systemctl --user list-units 'hermes*'` to find the right one.
- **The status-bar chip printed up to 200 characters into the status bar.** It shows the
  list name capped at 20 characters with an ellipsis; the full name stays in `title`.

### Changed
- Creating a list now reports `Opened "<name>"` instead of `Created`. `create_empty`
  returns an existing list when the name is already taken, and a stale poll cannot tell
  the two apart — "Opened" is true either way.

## 1.8.1 — 2026-11-08

Fixes from the seventh review (B1–B7).

### Fixed
- **B1 — `→` on a focused tab deleted the neighbouring tab.** `splice(indexOf(neighbour),
  delta < 0 ? 0 : 1, moved)` passes the second argument as *deleteCount*, not an offset,
  so a rightward nudge removed the neighbour from the payload; the server then appended
  the missing list at the far end. `←` was fine (`deleteCount 0`), and with two tabs the
  bug was invisible — which is why hand-testing passed.
- **B2 — `moveItem`'s catch cleared the error it had just set**, both in one React batch,
  so a failed row reorder showed nothing at all.
- **B3** — `deleteList`, `doExport` and `copyList` now clear a stale error too; they were
  the three success paths the earlier sweep missed.
- **B4** — `＋` on a collapsed pane flipped `aria-expanded` and showed nothing; it now
  expands the pane first.
- **B5** — creating a list whose name already existed toasted `Created "X"` while merely
  switching to it, and guessed the capitalisation instead of reading what the store kept.
  It now reports `Switched to` / `Created` from the API response.
- **B6** — the chip polls every 15s instead of 5s (it never sleeps, unlike the pane), names
  the list it is counting so it can't be confused with the tab on screen, and says so
  instead of dying silently on a desktop without `openWorkspace`.

### Changed
- **The reorder arithmetic is now two pure functions** (`applyMove`, `applySwap`) instead
  of four hand-rolled `splice` calls in four callbacks — the shape that produced B1.
  `tests/reorder.test.mjs` extracts them from `plugin.js` (a plugin cannot import its own
  siblings) and puts them under `node --test`, which now runs in CI. It asserts the case
  that shipped broken: no move may change the payload's length.

## 1.8.0 — 2026-11-08

### Added
- **New list from the pane** — `＋` in the header opens a naming row (Enter creates,
  Escape cancels); the list opens empty and becomes active. The API already had the
  empty-list path from the undo work.
- **Status-bar chip is back** — `☑ done/total`, click to open the pane. It was removed
  in 1.7.0 as a redundant second door, then missed the moment the tab was closed: the
  palette is the only other way in, and that is typing.
- **← / → reorders a focused tab**, matching what ↑ / ↓ already did for rows.

### Fixed
- **Dropping always inserted *before* the target**, so the last slot in a group was
  unreachable and a one-slot downward drag computed back to its own index and did
  nothing. The pointer's half of the row/tab now decides: left/upper lands before,
  right/lower lands after.
- **The error line never cleared.** A failure left the message on screen through every
  later success — a stale 404 looked like a live bug.
- Tab drags no longer depend on the insert index from the pre-removal array.

## 1.7.5 — 2026-11-08

README rewritten for people installing the plugin, not for reviewers.

- Removed the review-process sections (Known limits, Development) — the CI workflow is
  where that belongs, and a reader installing a checklist does not need the gate list.
- Removed the design-provenance table and the note about a feature that was never built.
  The README describes what the plugin does.
- Examples no longer borrow from one trade's vocabulary.
- The command palette shortcut is now stated for both platforms (Ctrl+K, ⌘K on macOS)
  rather than assuming one.
- Prose cut back; the API table kept, since those routes exist.

## 1.7.4 — 2026-11-08

Fixes from the fourth review (F1–F3) plus two nits.

### Fixed
- **F1 — the README still listed `PATCH /lists/order` as the tab-reorder route.** That
  path is now the *pin* route for a list named `order`, so a client following the
  docs would get a 200, pin a list, and not reorder anything. Row deleted.
- **F2 — test counts** corrected, then removed from the README entirely: the
  command is the information, and a hand-maintained number was wrong three releases
  running.
- **F3 — `art.py` resolved a second `core` module under the package load path.**
  `__init__.py` imports `.art` before `.core`, so art's probe ran before `ticklist.core`
  existed in `sys.modules` and fell through to a file load — two `TickError` classes in
  one process. The lookup now asks its own package first (`from . import core`), which
  is order-independent. Verified: identity `False` before the fix, `True` after, and a
  test asserts it in a synthetic package.

### Changed
- **"Remove from list on tick" is now undoable.** It deletes a row but never filled the
  undo slot, while the README promised undo after "removing one row". Same slot as a
  manual removal, same 12-second bar.
- `tick_delete_list` now carries the list inventory too — right after a delete is when
  "what's left" matters most.

## 1.7.3 — 2026-11-08

Fixes from the third review (R1–R5) plus documentation corrections.

### Fixed
- **R1 — a list named `order` could not be pinned, and the attempt silently reset
  the tab order.** `PATCH /lists/order` was captured by the tab-reorder route
  (static segment shadows `{name}`), so pinning a list called `order` wrote an empty
  tab order instead. Tab reordering moved to `PATCH /order`, and `ids` is now a
  required field so a stray body 422s rather than writing `[]`.
- **R2 — a partial tab order lost the user's arrangement.** The tail was rebuilt
  from a set (hash order). It now comes from the previous `order`, then any list not
  in it, so "these first, the rest keep their places" is true.
- **R3 — a long tab name clipped with no ellipsis.** The tab now truncates at 14rem
  with `text-overflow: ellipsis` (inline; a plugin class is never compiled).
- **R4 — the list inventory was attached to all six tools** (~1.2k tokens per call on
  a 49-list store). It now rides on `tick_list` only; the other five return the list
  they acted on.
- **R5 — `art`/`export` could resolve a second `core` module** under the package
  load path, giving two `TickError` classes in one process. The probe now also
  checks `ticklist.core`.
- `read()` no longer lists `JSONDecodeError` alongside `ValueError` (it is one).

### Docs
Corrected twelve statements that had drifted from the code: the grip is a focusable
handle, not a literal `<button>`, and why; JSON export is not importable; the
inventory is `tick_list`-only; list names are bounded at 200; tab truncation; what a
gateway restart does and doesn't buy; the `/lists` row shape; `create_empty`; the
missing `PATCH /lists/{name}` row; `?list=` takes an id; test counts (94); and the
guard runs five checks, not three.

## 1.7.2 — 2026-11-08

### Fixed
- **The whole plugin API failed to import on a real install (since 1.6.0).**
  `export.py` gained a dependency on `core.py` for the shared row order, and
  resolved it with `from .core import …` / `from core import …`. Both work when
  the file is imported as part of the package or from the repo root — and both
  fail when `plugin_api.py` loads it **by path**, which is how the plugin host does
  it. Every route, not just export, would have answered 500. The unit tests missed
  it because `test_core` had already put the repo root on `sys.path`; a read-only
  smoke over the real router caught it.
  Core is now resolved through `sys.modules` (`ticklist_core`), then the `core`
  name, then a sibling-file load — correct under all three loading paths.
- A new test runs `export.py` in a clean interpreter with no `PYTHONPATH` and no
  package context, so this cannot regress silently.
- `__init__.py` docstring said "five tools"; it registers six.

## 1.7.1 — 2026-11-08

### Added
- `tick_list` (and every tool payload) now returns `lists`: each list's name,
  `pinned` flag, done/total and whether it is the active one, in tab order. Until
  now the agent had no way to see pin state or to answer "what lists do I have" —
  the tools only ever returned the one list you asked for.

### Not changed, deliberately
- **Pinning does not post to the chat.** It is a view preference, not a change to
  the list's contents, and each post is a model turn. The state is readable
  through `tick_list` instead.

## 1.7.0 — 2026-11-08

### Added
- **Pinned tabs say so.** A pinned tab carries `📌` in front of its name, so the
  state reads at a glance instead of relying on position alone.
- **Tabs can be dragged to reorder.** The order is stored (`state["order"]`), not
  implied by creation time, so it survives restarts; `PATCH /lists/order` sets it.
  Tab drags stay inside their pinned group, for the same reason row drags do — the
  pinned-first sort would put a pinned tab straight back at the front.
- New lists join the end of the tab order; an id that doesn't exist, or a repeated
  one, is refused rather than silently dropped.

### Fixed
- The tab is a focusable `span` (role=button), not a `<button>`: Chromium will not
  start a drag from a button, which is what broke row dragging in 1.6.0.

## 1.6.0 — 2026-11-08

Fixes from the second review (N1–N10).

### Fixed
- **N1 — a list with a long name was visible and inert.** The store key came from
  the raw name while the display name was truncated at 60, so every lookup by the
  name the user could see failed: tick, untick, add, clear and undo all 404'd, and
  undoing a deleted long-named list created a *second* list beside it. Names are no
  longer truncated in the store at all (200 characters, then refused), and lookups
  fall back to a display-name match for stores written before this change.
- **N2 — `replace_items()` accepted duplicate ids**, which locks the list out of
  reorder permanently (the id→row map collapses, so the count check can never pass
  again). Duplicates are refused; `created`/`done_at` are coerced instead of raising.
- **N3 — a parseable store with one bad value bricked every route.** `created_at:
  "not-a-number"` gave a 500 on `/lists` and a false `/health`. Timestamps are now
  coerced on read, per-list failures are skipped, and `read()` quarantines rather
  than propagating.
- **N4 — downward drags landed one slot too far.** Removing the source shifts the
  indices, so inserting at the target's original index put the row *below* the one
  the indicator pointed above.
- **N5 — the whole row was draggable, not the grip**, which killed text selection.
  Only the grip starts a drag now, it is a focusable button, and ↑/↓ reorders.
- **N6 — undo lost `created`/`done_at`** because the row payload omitted them, so
  a restored tick had no completion time and the CSV columns changed.
- **N7 — undo of a deleted empty list** failed: `POST /lists` demanded an item. It
  takes `create_empty`.
- **N8 — export order differed from the checklist order.** `core.ordered_items()`
  is now the one implementation, used by the pane's sort, the art and the exports.
- **N9 — CSV formula injection**: cells starting `= + - @` are prefixed with `'`.
- **N10** — header comment no longer mentions the removed chip; the guard's variant
  regex is anchored; clipboard uses `ctx.os.writeClipboard` where available; the
  false "optimistic" comment is gone; the export menu closes on Escape.

## 1.5.0 — 2026-11-08

### Changed
- **Undo covers every destructive action, not just deleting a list.** Clearing
  ticked rows and removing a single row now offer the same 12-second bar.
  `core.replace_items()` plus `PATCH /lists/{name}/items` write the snapshot back
  verbatim — same ids, order, timestamps and tick states — instead of re-adding
  lookalike rows at the end of the list. The bar's label names what it is undoing
  (`Cleared 4 ticked`, `Removed "paint"`, `Deleted "Two"`).

### Fixed
- The undo handler shadowed the pane's own `rows` binding; renamed to `snapshot`.

## 1.4.0 — 2026-11-08

### Added
- **A visible drag affordance** — `⠿` grip at the head of every row, always shown.
  A row you can drag but can't tell is draggable is a row nobody drags.
- **Pin a list** (📌) — pinned lists sort to the front of the tab strip and keep
  their relative order; `pinned` lives in the store, so it survives restarts.
- **Clear N ticked** — a button under the strip that empties the finished rows for
  the list on screen (the `tick_clear done_only` tool existed; the pane never
  exposed it), announced in the chat.
- **Undo after deleting a list** — a 12-second bar that restores the list with its
  rows and their tick states. The window closes on its own rather than offering a
  stale restore later.

### Fixed
- The API payload didn't apply the pinned-first ordering, so the pane would have
  shown pins doing nothing. Both `summary()` and the routes now share
  `core.ordered_entries()`.

## 1.3.0 — 2026-11-08

### Added
- **Drag to reorder rows.** Dragging is confined to a row's own group — dropping an
  unticked row among the ticked ones would be undone by the sort on the next poll,
  so the drop line only appears where the move can hold. Order is written to the
  store via `PATCH /lists/{name}/order`; the endpoint refuses a partial or
  duplicated order rather than silently re-appending the missing rows.
- **Export a list**: Text, Markdown (task-list), CSV, JSON, or copy to the
  clipboard, from `⤓` in the header. `GET /lists/{name}/export?fmt=` serves it.

## 1.2.0 — 2026-11-08

### Added
- **Delete a whole list.** `×` on the active tab, with an inline confirmation that
  names the list and how many items go with it; the deletion is announced in the
  chat (`Deleted list — Beer run (5 items)`). Backed by `DELETE /lists/{name}` and a
  sixth tool, `tick_delete_list`, so the agent can do the same thing when asked.
- Deleting the active list moves `active` to a surviving list; deleting the last one
  leaves an empty store that does not re-seed the example.

## 1.1.3 — 2026-11-08

### Added
- **Example list on first run** — "First ticks": seven rows that each show a feature
  (tick → the agent hears it, untick → nothing is permanent, tabs, delete the list),
  two of them pre-ticked so the strike-through and the sort order are visible.
  Seeded behind a `.seeded` marker, so a used store is never touched and deleting
  the example is permanent.

## 1.1.2 — 2026-11-08

### Fixed
- **The Add button rendered as bare text.** It was created with
  `variant: 'primary'`, which is not a `Button` variant in this app (`default`,
  `secondary`, `outline`, `chip`, `ghost`, … are) — an unknown variant compiles to
  no classes at all. It is now the real filled `default` button.
- **New list titles start with a capital.** Models name lists in lowercase
  (`vehicles`), so the tab strip read like a bug. `clean_name` capitalises an
  all-lowercase opening word and leaves `DIY`/`iPad` alone; the store key is
  unaffected.

### Added
- The guard now also rejects a `Button` `variant`/`size` the app doesn't define —
  the same silent-nothing failure as a Tailwind class that never gets compiled.

## 1.1.1 — 2026-11-08

Fixes from an external review of 1.1.0 (issue #1).

### Fixed
- **The tab underline never drew.** `border-b-2` is a Tailwind class the app never
  compiles for a plugin file, so the active-tab accent was invisible. Now an inline
  `borderBottom`.
- **"Remove from list on tick" had no UI.** The setter was declared, persisted and
  documented in three places, but nothing rendered the checkbox — it is back above
  the add box.
- **Long list names could merge.** `slugify()` truncated at 48 while names allowed
  60, so two names sharing a prefix collapsed into one list with the second one's
  items inside the first. Keys are now derived from the raw name and a truncated key
  keeps a hash suffix. Display names show an ellipsis when cut.
- **A corrupt store was a silent wipe.** `read()` returned an empty state and the
  next write replaced the file. The unparseable file is now moved to
  `lists.json.corrupt-<epoch>` before an empty state is returned.
- **`items` as an object stored an item named "text"** (a dict iterates its keys).
  Mappings are refused with a hint to wrap the item in a list.
- Row delete button is reachable by keyboard (`focus-visible`) and has an
  `aria-label`; the announce toggle exposes `aria-pressed`.
- `PATCH /items/{id}` answers 400, not 404, for a missing id.
- Guard (`scripts/check_setters.py`) now also flags a setter that is declared but
  never called — the shape that let the missing checkbox ship.
- README: "Reload desktop plugins" **does** exist (it was documented as absent);
  install steps now say the desktop app must reconcile before the pane appears.

## 1.1.0 — 2026-11-08

Second release: the pane became a first-class Hermes pane, and the poll stopped
scaling with the store.

### Added
- **List tabs** — a scrollable strip, one tab per list with `done/total`; wraps and
  scrolls vertically past five rows.
- **"Remove from list on tick"** option, off by default, persisted in `ctx.storage`.
- `GET /lists/{name}` — one list with its rows, fetched on tab switch.
- `tests/` is a package and CI runs core + API tests on Python 3.10 and 3.13.
- Mount-time guard (`scripts/check_setters.py`) for dead setters, unimported hooks
  and quoted area constants.

### Changed
- The pane opens through `host.openWorkspace` and **docks in the terminal pane's
  zone as a sibling tab** (`dock: {pane: 'terminal', pos: 'center', enforce: true}`)
  with a `minWidth` floor, replacing the `panes`-area registration that could not be
  reopened from a click handler.
- `GET /lists` returns summaries, not every row of every list: **19.8 KiB → 2.6 KiB**
  per poll on a 22-list store, **7.6 MiB → 0.18 MiB** at the 50 × 2,000 ceiling.
- The store is read once per request instead of once per list (8.0 ms → 0.4 ms).
- Item text longer than the render width is ellipsised instead of cut mid-word.
- Unticked items sort above ticked ones, stably, on both the pane and text surfaces.

### Removed
- **Status-bar chip.** It existed to summon a pane that could vanish into Settings;
  once the pane was a permanent tab it was a second door for something one click
  away.
- `core.format_list` (dead — `art.render_list` serves every text surface).

### Fixed
- `PATCH`/`DELETE /items/{id}` without `?list=` searched the *active* list, not the
  tab on screen, giving `404 no item matching '<id>'` for any other list.
- Reopening the pane snapped back to the backend's "active" list; the selection is
  now persisted.
- `GET /health` echoed the store's absolute path to any dashboard client.
- `tick_add` reported `skipped` in characters for multi-line input.
- `useEffect` was used without being imported, crashing the pane on mount.

## 1.0.0 — 2026-11-08

First release: five tools, a bundled skill, `/tick`, a Desktop pane of checkboxes
that posts each tick into the conversation, an atomic JSON store shared by the pane
and the agent, and a column-0 text checklist for CLI/TUI/Discord.
