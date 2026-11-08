# Changelog

All notable changes to this plugin. Versions follow the `plugin.yaml` version.

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
