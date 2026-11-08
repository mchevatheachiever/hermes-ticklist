/**
 * TickList — desktop half.
 *
 * A pane of checkboxes. Every tick or untick is posted into the conversation as
 * it happens, so the agent sees the change without being asked. The pane opens
 * through `host.openWorkspace` and docks beside the terminal pane; the tab's own
 * Close tears it down, and the palette row re-opens it by the same id.
 *
 * Plain ESM, loaded uncompiled: jsx() calls, no JSX syntax.
 * Only @hermes/plugin-sdk, react and react/jsx-runtime resolve.
 */

import { Button, cn, haptic, host, PALETTE_AREA, useQuery } from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'
import { useCallback, useEffect, useState } from 'react'

const ID = 'ticklist'

function Row({
  item,
  onToggle,
  onRemove,
  onDragStart,
  onDragOver,
  onDrop,
  onNudge,
  dragging,
  dropTarget
}) {
  const [busy, setBusy] = useState(false)
  return jsxs('div', {
    className: 'group flex items-start gap-2 rounded px-1 py-1 hover:bg-(--chrome-action-hover)',
    // Drop target: the whole row accepts a drop, the grip starts the drag.
    onDragOver: (event) => {
      event.preventDefault()
      event.dataTransfer.dropEffect = 'move'
      onDragOver(item)
    },
    onDrop: (event) => {
      event.preventDefault()
      onDrop(item)
    },
    style: {
      opacity: dragging ? 0.4 : 1,
      // A line where the row will land — inline, because a plugin's own Tailwind
      // class would never be compiled into the app's CSS.
      boxShadow: dropTarget ? 'inset 0 2px 0 0 var(--ui-accent)' : 'none'
    },
    children: [
      // The grip is the handle — only it is draggable, so item text stays
      // selectable and copyable. It must NOT be a <button>: Chromium refuses to
      // start a drag from one. A focusable span with role=button gets the
      // keyboard path without the dead spot.
      jsx('span', {
        role: 'button',
        tabIndex: 0,
        draggable: true,
        title: 'Drag to reorder, or focus and press ↑ ↓',
        'aria-label': `Reorder ${item.text}. Use the up and down arrows.`,
        onDragStart: (event) => {
          event.dataTransfer.effectAllowed = 'move'
          // Firefox needs data set for a drag to start at all.
          event.dataTransfer.setData('text/plain', item.id)
          onDragStart(item)
        },
        onDragEnd: () => onDragStart(null),
        onKeyDown: (event) => {
          if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
            event.preventDefault()
            onNudge(item, event.key === 'ArrowUp' ? -1 : 1)
          }
        },
        style: {
          flex: '0 0 auto',
          width: '12px',
          marginTop: '1px',
          padding: 0,
          border: 'none',
          background: 'transparent',
          color: 'var(--ui-text-quaternary)',
          fontSize: '11px',
          lineHeight: '17px',
          cursor: 'grab',
          userSelect: 'none'
        },
        children: '⠿'
      }),
      jsx('button', {
        type: 'button',
        'aria-label': item.done ? `Untick ${item.text}` : `Tick ${item.text}`,
        disabled: busy,
        onClick: async () => {
          setBusy(true)
          try {
            await onToggle(item)
          } finally {
            setBusy(false)
          }
        },
        style: {
          flex: '0 0 auto',
          width: '17px',
          height: '17px',
          marginTop: '1px',
          borderRadius: '4px',
          border: `1px solid ${item.done ? 'var(--ui-accent)' : 'var(--ui-stroke-secondary)'}`,
          background: item.done ? 'var(--ui-accent)' : 'transparent',
          color: 'var(--ui-bg, #111)',
          fontSize: '12px',
          lineHeight: 1,
          fontWeight: 800,
          cursor: busy ? 'wait' : 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        },
        children: item.done ? '✓' : ''
      }),
      jsx('span', {
        className: 'min-w-0 flex-1 text-[0.8125rem] leading-snug',
        style: {
          color: item.done ? 'var(--ui-text-quaternary)' : 'var(--ui-text-secondary)',
          textDecoration: item.done ? 'line-through' : 'none',
          overflowWrap: 'anywhere'
        },
        children: item.text
      }),
      jsx('button', {
        type: 'button',
        title: 'Remove item',
        'aria-label': `Remove ${item.text}`,
        onClick: () => onRemove(item),
        className:
          'shrink-0 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 text-(--ui-text-quaternary) hover:text-foreground',
        style: { fontSize: '11px', padding: '0 3px' },
        children: '✕'
      })
    ]
  })
}

function TickPane({ ctx }) {
  const [collapsed, setCollapsed] = useState(false)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')
  const [selected, setSelected] = useState('')
  const [announce, setAnnounce] = useState(true)
  const [removeOnTick, setRemoveOnTick] = useState(false)
  const [pendingDelete, setPendingDelete] = useState('')
  const [dragId, setDragId] = useState('')
  const [overId, setOverId] = useState('')
  const [exportOpen, setExportOpen] = useState(false)
  const [tabDragId, setTabDragId] = useState('')
  const [tabOverId, setTabOverId] = useState('')
  const [lastAction, setLastAction] = useState(null)

  // Remembered across sessions; the pane state is scratch, this is the setting.
  useEffect(() => {
    let cancelled = false
    try {
      Promise.resolve(ctx.storage.get('removeOnTick'))
        .then((value) => {
          if (!cancelled && value === true) setRemoveOnTick(true)
        })
        .catch(() => {})
      // Re-opening the pane remounts this component, so the tab you were on is
      // gone unless it is stored: without this the pane snaps back to whatever
      // the backend calls "active" (the last list written to).
      Promise.resolve(ctx.storage.get('selectedList'))
        .then((value) => {
          if (!cancelled && typeof value === 'string' && value) setSelected(value)
        })
        .catch(() => {})
    } catch {
      /* no storage on an old shell — default stays off */
    }
    return () => {
      cancelled = true
    }
  }, [ctx])

  const setRemovePref = useCallback(
    (value) => {
      setRemoveOnTick(value)
      try {
        Promise.resolve(ctx.storage.set('removeOnTick', value)).catch(() => {})
      } catch {
        /* non-fatal */
      }
    },
    [ctx]
  )

  const query = useQuery({
    queryKey: ['ticklist', 'lists'],
    queryFn: () => ctx.rest('/lists'),
    refetchInterval: 3000,
    retry: 1
  })

  const state = query.data || { lists: [], active: '' }
  const list =
    state.lists.find((entry) => entry.id === selected) ||
    state.lists.find((entry) => entry.id === state.active) ||
    state.lists[0] ||
    null

  // The poll above carries names and counts only. Rows come from the one list
  // being shown, so a store full of long lists no longer ships on every tick.
  const listId = list ? list.id : ''
  const detail = useQuery({
    queryKey: ['ticklist', 'list', listId],
    queryFn: () =>
      listId
        ? ctx.rest(`/lists/${encodeURIComponent(listId)}`)
        : Promise.resolve({ ok: true, list: null }),
    enabled: Boolean(listId),
    refetchInterval: 3000,
    retry: 1
  })
  const fresh = detail.data && detail.data.list && detail.data.list.id === listId ? detail.data.list : null
  const rows = (fresh && fresh.items) || (list && list.items) || []

  // unticked first, ticked gathered at the bottom (stable within each group)
  const items = [...rows].sort((a, b) => Number(a.done) - Number(b.done))
  const done = list ? list.done : 0
  const total = list ? list.total : 0

  const refresh = useCallback(() => {
    query.refetch()
    detail.refetch()
  }, [query, detail])

  // A tick names its list explicitly: the API falls back to the *active* list,
  // which is whichever list was last created or added to — not the tab in view.
  const listPath = useCallback(
    (itemId) => {
      const suffix = list ? `?list=${encodeURIComponent(list.id)}` : ''
      return `/items/${encodeURIComponent(itemId)}${suffix}`
    },
    [list]
  )

  const post = useCallback(
    (text) => {
      if (!announce) return
      try {
        const sent =
          host.composer && host.composer.submit ? host.composer.submit(null, text) : false
        if (sent === false) host.notify({ kind: 'info', message: text })
      } catch {
        host.notify({ kind: 'info', message: text })
      }
    },
    [announce]
  )

  const toggle = useCallback(
    async (item) => {
      haptic('tap')
      try {
        if (!item.done && removeOnTick) {
          await ctx.rest(listPath(item.id), { method: 'DELETE' })
          refresh()
          post(`Ticked and removed — ${item.text}`)
          return
        }
        await ctx.rest(listPath(item.id), {
          method: 'PATCH',
          body: { done: !item.done }
        })
        refresh()
        post(`${item.done ? 'Unticked' : 'Ticked'} — ${item.text}`)
      } catch (err) {
        setError(`could not save: ${err && err.message ? err.message : err}`)
      }
    },
    [ctx, listPath, post, refresh, removeOnTick]
  )

  const remove = useCallback(
    async (item) => {
      const snapshot = rows
      const name = list ? list.name : ''
      try {
        await ctx.rest(listPath(item.id), { method: 'DELETE' })
        setLastAction({ kind: 'remove', name, id: list ? list.id : '', rows: snapshot, label: `Removed "${item.text}"` })
        refresh()
        post(`Removed — ${item.text}`)
      } catch (err) {
        setError(`could not remove: ${err && err.message ? err.message : err}`)
      }
    },
    [ctx, list, listPath, post, refresh, rows]
  )

  const deleteList = useCallback(async () => {
    if (!list) return
    const name = list.name
    const count = total
    const snapshot = rows
    try {
      await ctx.rest(`/lists/${encodeURIComponent(list.id)}`, { method: 'DELETE' })
      setPendingDelete('')
      setSelected('')
      setLastAction({ kind: 'delete', name, id: list.id, rows: snapshot, label: `Deleted "${name}"` })
      try {
        Promise.resolve(ctx.storage.set('selectedList', '')).catch(() => {})
      } catch {
        /* non-fatal */
      }
      refresh()
      post(`Deleted list — ${name} (${count} item${count === 1 ? '' : 's'})`)
    } catch (err) {
      setError(`could not delete: ${err && err.message ? err.message : err}`)
    }
  }, [ctx, list, post, refresh, rows, total])

  const togglePin = useCallback(async () => {
    if (!list) return
    haptic('tap')
    try {
      await ctx.rest(`/lists/${encodeURIComponent(list.id)}`, {
        method: 'PATCH',
        body: { pinned: !list.pinned }
      })
      refresh()
    } catch (err) {
      setError(`could not pin: ${err && err.message ? err.message : err}`)
    }
  }, [ctx, list, refresh])

  const clearTicked = useCallback(async () => {
    if (!list) return
    const count = done
    const name = list.name
    const snapshot = rows
    try {
      await ctx.rest(`/clear?list=${encodeURIComponent(list.id)}`, {
        method: 'POST',
        body: { done_only: true }
      })
      setLastAction({ kind: 'clear', name, id: list.id, rows: snapshot, label: `Cleared ${count} ticked` })
      refresh()
      post(`Cleared ${count} ticked from ${name}`)
    } catch (err) {
      setError(`could not clear: ${err && err.message ? err.message : err}`)
    }
  }, [ctx, done, list, post, refresh, rows])

  const undoLast = useCallback(async () => {
    if (!lastAction) return
    const { kind, name, id, rows: snapshot } = lastAction
    try {
      if (kind === 'delete') {
        // The list itself is gone, so recreate it, then overwrite the rows with
        // the snapshot to put the ids, order and timestamps back exactly.
        // An empty list has no rows to re-add, so ask for the list itself.
        await ctx.rest('/lists', {
          method: 'POST',
          body: snapshot.length
            ? { list: name, items: snapshot }
            : { list: name, create_empty: true }
        })
      }
      await ctx.rest(`/lists/${encodeURIComponent(id)}/items`, {
        method: 'PATCH',
        body: { items: snapshot }
      })
      setLastAction(null)
      refresh()
      post(`Restored — ${name}`)
    } catch (err) {
      setError(`could not restore: ${err && err.message ? err.message : err}`)
    }
  }, [ctx, lastAction, post, refresh])

  // The undo window closes on its own; a stale offer to restore is worse than
  // no offer at all once other work has happened.
  useEffect(() => {
    if (!exportOpen) return undefined
    const onKey = (event) => {
      if (event.key === 'Escape') setExportOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [exportOpen])

  useEffect(() => {
    if (!lastAction) return undefined
    const timer = setTimeout(() => setLastAction(null), 12000)
    return () => clearTimeout(timer)
  }, [lastAction])

  const moveItem = useCallback(
    async (fromId, toId) => {
      if (!fromId || !toId || fromId === toId || !list) return
      const order = items.map((item) => item.id)
      const from = order.indexOf(fromId)
      const to = order.indexOf(toId)
      if (from < 0 || to < 0) return
      const [moved] = order.splice(from, 1)
      // Removing the source shifts everything above it, so a downward move has
      // to land one slot earlier than the target's original index — otherwise
      // the row lands *below* the one the indicator pointed above.
      order.splice(from < to ? to - 1 : to, 0, moved)
      try {
        await ctx.rest(`/lists/${encodeURIComponent(list.id)}/order`, {
          method: 'PATCH',
          body: { ids: order }
        })
        refresh()
      } catch (err) {
        setError(`could not reorder: ${err && err.message ? err.message : err}`)
        refresh()
      }
    },
    [ctx, items, list, refresh]
  )

  // Tab drags stay inside a pinned group for the same reason row drags do: the
  // pinned-first sort would put a pinned tab straight back at the front.
  const moveTab = useCallback(
    (fromId, toId) => {
      if (!fromId || !toId || fromId === toId) return
      const order = state.lists.map((entry) => entry.id)
      const from = order.indexOf(fromId)
      const to = order.indexOf(toId)
      if (from < 0 || to < 0) return
      const [moved] = order.splice(from, 1)
      order.splice(from < to ? to - 1 : to, 0, moved)
      ctx
        .rest('/order', { method: 'PATCH', body: { ids: order } })
        .then(refresh)
        .catch((err) => setError(`could not reorder tabs: ${err && err.message ? err.message : err}`))
    },
    [ctx, refresh, state.lists]
  )

  const nudge = useCallback(
    (item, delta) => {
      const group = items.filter((entry) => entry.done === item.done)
      const at = group.findIndex((entry) => entry.id === item.id)
      const neighbour = group[at + delta]
      if (!neighbour) return
      const order = items.map((entry) => entry.id)
      const from = order.indexOf(item.id)
      const to = order.indexOf(neighbour.id)
      const [moved] = order.splice(from, 1)
      order.splice(to, 0, moved)
      haptic('tap')
      if (!list) return
      ctx
        .rest(`/lists/${encodeURIComponent(list.id)}/order`, { method: 'PATCH', body: { ids: order } })
        .then(refresh)
        .catch((err) => setError(`could not reorder: ${err && err.message ? err.message : err}`))
    },
    [ctx, items, list, refresh]
  )

  const doExport = useCallback(
    async (fmt) => {
      setExportOpen(false)
      if (!list) return
      try {
        const result = await ctx.rest(
          `/lists/${encodeURIComponent(list.id)}/export?fmt=${fmt}`
        )
        const blob = new Blob([result.content], { type: result.mime })
        const url = URL.createObjectURL(blob)
        const anchor = document.createElement('a')
        anchor.href = url
        anchor.download = result.filename
        document.body.appendChild(anchor)
        anchor.click()
        anchor.remove()
        setTimeout(() => URL.revokeObjectURL(url), 1000)
        host.notify({ kind: 'info', message: `Exported ${result.filename}` })
      } catch (err) {
        setError(`could not export: ${err && err.message ? err.message : err}`)
      }
    },
    [ctx, list]
  )

  const copyList = useCallback(async () => {
    setExportOpen(false)
    if (!list) return
    try {
      const result = await ctx.rest(`/lists/${encodeURIComponent(list.id)}/export?fmt=txt`)
      if (ctx.os && typeof ctx.os.writeClipboard === 'function') {
        await ctx.os.writeClipboard(result.content)
      } else {
        await navigator.clipboard.writeText(result.content)
      }
      host.notify({ kind: 'info', message: 'List copied to the clipboard' })
    } catch (err) {
      setError(`could not copy: ${err && err.message ? err.message : err}`)
    }
  }, [ctx, list])

  const add = useCallback(async () => {
    const lines = draft
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
    if (!lines.length) return
    try {
      await ctx.rest('/lists', {
        method: 'POST',
        body: { items: lines, list: list ? list.name : undefined }
      })
      setDraft('')
      setError('')
      haptic('tap')
      refresh()
      post(lines.length === 1 ? `Added — ${lines[0]}` : `Added ${lines.length} items`)
    } catch (err) {
      setError(`could not add: ${err && err.message ? err.message : err}`)
    }
  }, [ctx, draft, list, post, refresh])

  // ---- header: collapse, close, list switcher ---------------------------- #

  const header = jsxs('div', {
    className: 'flex items-center gap-1.5',
    children: [
      jsx('button', {
        type: 'button',
        title: collapsed ? 'Expand' : 'Collapse',
        onClick: () => setCollapsed((value) => !value),
        className: 'shrink-0 text-(--ui-text-tertiary) hover:text-foreground',
        style: { fontSize: '11px', padding: '0 2px' },
        children: collapsed ? '▸' : '▾'
      }),
      jsx('span', {
        className: 'min-w-0 flex-1 truncate font-medium',
        children: list ? list.name : 'ticklist'
      }),
      jsx('span', {
        className: 'shrink-0 text-[0.625rem] text-(--ui-text-quaternary)',
        children: `${done}/${total}`
      }),
      jsx(Button, {
        size: 'xs',
        variant: 'ghost',
        onClick: togglePin,
        title: list && list.pinned ? 'Unpin this list' : 'Pin this list to the front',
        'aria-label': list && list.pinned ? 'Unpin this list' : 'Pin this list to the front',
        'aria-pressed': Boolean(list && list.pinned),
        style: { opacity: list && list.pinned ? 1 : 0.45 },
        children: '📌'
      }),
      jsx(Button, {
        size: 'xs',
        variant: 'ghost',
        onClick: () => setExportOpen((value) => !value),
        title: 'Export this list',
        'aria-label': 'Export this list',
        'aria-expanded': exportOpen,
        children: '⤓'
      }),
      jsx(Button, {
        size: 'xs',
        variant: 'ghost',
        onClick: () => setAnnounce((value) => !value),
        title: announce ? 'Ticks are posted to the chat' : 'Ticks stay in the pane',
        'aria-label': announce ? 'Stop posting ticks to the chat' : 'Post ticks to the chat',
        'aria-pressed': announce,
        children: announce ? '💬' : '🔇'
      }),
    ]
  })

  if (collapsed) {
    return jsx('div', {
      className: 'flex h-full flex-col p-2 text-sm',
      children: header
    })
  }

  // A scrollable tab strip: every list is reachable, however many there are.
  const showTabs = state.lists.length > 1

  return jsxs('div', {
    className: 'flex h-full min-h-0 flex-col gap-1.5 overflow-hidden p-2 text-sm',
    style: { minWidth: '18rem', width: '100%' },
    children: [
      header,

      exportOpen && list
        ? jsxs('div', {
            className:
              'flex shrink-0 flex-wrap items-center gap-1 rounded bg-(--ui-bg-quaternary) px-2 py-1',
            children: [
              jsx('span', {
                className: 'text-[0.625rem] text-(--ui-text-quaternary)',
                children: 'Export'
              }),
              jsx(Button, {
                size: 'micro',
                variant: 'secondary',
                onClick: () => doExport('txt'),
                children: 'Text'
              }),
              jsx(Button, {
                size: 'micro',
                variant: 'secondary',
                onClick: () => doExport('md'),
                children: 'Markdown'
              }),
              jsx(Button, {
                size: 'micro',
                variant: 'secondary',
                onClick: () => doExport('csv'),
                children: 'CSV'
              }),
              jsx(Button, {
                size: 'micro',
                variant: 'secondary',
                onClick: () => doExport('json'),
                children: 'JSON'
              }),
              jsx(Button, {
                size: 'micro',
                variant: 'ghost',
                onClick: copyList,
                children: 'Copy'
              })
            ]
          })
        : null,

      showTabs
        ? jsx('div', {
            // Wrap, then scroll vertically: five rows (~7rem at this tab height)
            // is the ceiling before the strip starts scrolling instead of growing.
            className: 'flex shrink-0 flex-wrap gap-1 pb-0.5',
            style: { scrollbarWidth: 'thin', maxHeight: '7rem', overflowY: 'auto' },
            children: state.lists.map((entry) =>
              jsxs(
                'div',
                {
                  className: 'flex shrink-0 items-center',
                  // Drop target for a tab drag; the tab itself starts the drag.
                  onDragOver: (event) => {
                    event.preventDefault()
                    event.dataTransfer.dropEffect = 'move'
                    const source = state.lists.find((item) => item.id === tabDragId)
                    if (source && source.pinned === entry.pinned && source.id !== entry.id) {
                      setTabOverId(entry.id)
                    } else {
                      setTabOverId('')
                    }
                  },
                  onDrop: (event) => {
                    event.preventDefault()
                    const source = state.lists.find((item) => item.id === tabDragId)
                    setTabOverId('')
                    setTabDragId('')
                    if (source && source.pinned === entry.pinned) moveTab(source.id, entry.id)
                  },
                  style: {
                    opacity: tabDragId === entry.id ? 0.4 : 1,
                    boxShadow:
                      tabOverId === entry.id ? 'inset 2px 0 0 0 var(--ui-accent)' : 'none'
                  },
                  children: [
                    // A span, not a button: Chromium refuses to start a drag from
                    // a <button>, and tabs have to be draggable.
                    jsx('span', {
                      role: 'button',
                      tabIndex: 0,
                      draggable: true,
                      title: entry.pinned
                        ? `${entry.name} — pinned. Drag to reorder, click to open.`
                        : `${entry.name} — drag to reorder, click to open.`,
                      'aria-label': `${entry.name}, ${entry.done} of ${entry.total} done${
                        entry.pinned ? ', pinned' : ''
                      }`,
                      onClick: () => {
                        setSelected(entry.id)
                        try {
                          Promise.resolve(ctx.storage.set('selectedList', entry.id)).catch(() => {})
                        } catch {
                          /* non-fatal: the tab just won't be remembered */
                        }
                      },
                      onKeyDown: (event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          setSelected(entry.id)
                        }
                      },
                      onDragStart: (event) => {
                        event.dataTransfer.effectAllowed = 'move'
                        event.dataTransfer.setData('text/plain', entry.id)
                        setTabDragId(entry.id)
                      },
                      onDragEnd: () => {
                        setTabDragId('')
                        setTabOverId('')
                      },
                      className: cn(
                        'shrink-0 whitespace-nowrap rounded-t px-2 py-1 text-[0.6875rem] transition-colors',
                        entry.id === (list && list.id)
                          ? 'text-foreground'
                          : 'text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover)'
                      ),
                      // Inline, not `border-b-2`: Tailwind v4 only compiles classes
                      // found under apps/desktop/src, so a plugin class never exists.
                      style: {
                        borderBottom: `2px solid ${
                          entry.id === (list && list.id) ? 'var(--ui-accent)' : 'transparent'
                        }`,
                        cursor: 'grab',
                        userSelect: 'none',
                        // The tab strip never truncates a 200-char name by
                        // itself; inline because a plugin's own class is never
                        // compiled into the app's CSS.
                        maxWidth: '14rem',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        display: 'inline-block',
                        verticalAlign: 'bottom'
                      },
                      children: `${entry.pinned ? '📌 ' : ''}${entry.name} (${entry.done}/${entry.total})`
                    }),
                    entry.id === (list && list.id)
                      ? jsx('button', {
                          type: 'button',
                          title: `Delete the list "${entry.name}"`,
                          'aria-label': `Delete the list ${entry.name}`,
                          onClick: () => {
                            haptic('tap')
                            setPendingDelete(entry.id)
                          },
                          className:
                            'shrink-0 px-1 pb-0.5 text-[0.75rem] leading-none text-(--ui-text-quaternary) hover:text-foreground',
                          children: '×'
                        })
                      : null
                  ]
                },
                entry.id
              )
            )
          })
        : null,

      done > 0
        ? jsx('div', {
            className: 'flex shrink-0 justify-end',
            children: jsx(Button, {
              size: 'micro',
              variant: 'ghost',
              onClick: clearTicked,
              'aria-label': `Clear ${done} ticked item${done === 1 ? '' : 's'}`,
              children: `Clear ${done} ticked`
            })
          })
        : null,

      lastAction
        ? jsxs('div', {
            className:
              'flex shrink-0 flex-wrap items-center gap-1.5 rounded bg-(--ui-bg-quaternary) px-2 py-1 text-[0.6875rem]',
            children: [
              jsx('span', {
                className: 'min-w-0 flex-1 truncate',
                children: lastAction.label
              }),
              jsx(Button, {
                size: 'micro',
                variant: 'secondary',
                onClick: undoLast,
                children: 'Undo'
              })
            ]
          })
        : null,

      pendingDelete && list && pendingDelete === list.id
        ? jsxs('div', {
            className:
              'flex shrink-0 flex-wrap items-center gap-1.5 rounded bg-(--ui-bg-quaternary) px-2 py-1 text-[0.6875rem]',
            children: [
              jsx('span', {
                className: 'min-w-0 flex-1 truncate',
                children: `Delete "${list.name}" and its ${total} item${total === 1 ? '' : 's'}?`
              }),
              jsx(Button, {
                size: 'micro',
                variant: 'destructive',
                onClick: deleteList,
                children: 'Delete'
              }),
              jsx(Button, {
                size: 'micro',
                variant: 'ghost',
                onClick: () => setPendingDelete(''),
                children: 'Cancel'
              })
            ]
          })
        : null,

      jsx('div', {
        className: 'min-h-0 flex-1 overflow-y-auto',
        children: items.length
          ? jsx('div', {
              className: 'flex flex-col gap-0.5',
              children: items.map((item) =>
                jsx(
                  Row,
                  {
                    item,
                    onToggle: toggle,
                    onRemove: remove,
                    onNudge: nudge,
                    dragging: dragId === item.id,
                    dropTarget: Boolean(
                      overId === item.id &&
                        dragId &&
                        dragId !== item.id &&
                        (items.find((entry) => entry.id === dragId) || {}).done === item.done
                    ),
                    onDragStart: (source) => {
                      setDragId(source ? source.id : '')
                      if (!source) setOverId('')
                    },
                    onDragOver: (target) => {
                      const source = items.find((entry) => entry.id === dragId)
                      // Only within a group: dropping an unticked row among the
                      // ticked ones would be undone by the sort on the next poll.
                      if (source && source.done === target.done) setOverId(target.id)
                      else setOverId('')
                    },
                    onDrop: (target) => {
                      const source = items.find((entry) => entry.id === dragId)
                      setOverId('')
                      setDragId('')
                      if (source && source.done === target.done) moveItem(source.id, target.id)
                    }
                  },
                  item.id
                )
              )
            })
          : jsx('div', {
              className: 'p-2 text-center text-[0.6875rem] text-(--ui-text-quaternary)',
              children: list
                ? 'Nothing on the list. Add something below, or ask Hermes.'
                : 'No list yet. Type below, or ask Hermes to make one.'
            })
      }),

      jsxs('label', {
        className:
          'flex shrink-0 cursor-pointer items-center gap-1.5 text-[0.6875rem] text-(--ui-text-tertiary)',
        style: { userSelect: 'none' },
        children: [
          jsx('input', {
            type: 'checkbox',
            checked: removeOnTick,
            onChange: (event) => setRemovePref(event.target.checked),
            style: { accentColor: 'var(--ui-accent)', width: '12px', height: '12px' }
          }),
          jsx('span', { children: 'remove from list on tick' })
        ]
      }),

      jsxs('div', {
        className: 'flex shrink-0 flex-col gap-1',
        children: [
          jsx('textarea', {
            value: draft,
            onChange: (event) => setDraft(event.target.value),
            onKeyDown: (event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                add()
              }
            },
            placeholder: 'Add an item… (Enter)',
            className:
              'h-14 w-full resize-none rounded border border-(--ui-stroke-secondary) bg-transparent p-1.5 text-xs outline-none',
            style: { color: 'var(--ui-text-secondary)' }
          }),
          jsx(Button, {
            size: 'sm',
            variant: 'default',
            onClick: add,
            disabled: !draft.trim(),
            className: 'w-full font-medium',
            'aria-label': 'Add item',
            children: 'Add'
          })
        ]
      }),

      error
        ? jsx('div', {
            className: 'truncate text-center text-[0.6875rem]',
            style: { color: 'var(--ui-text-secondary)' },
            children: error
          })
        : null,

      query.isError
        ? jsx('div', {
            className: 'text-[0.6875rem] text-(--ui-text-quaternary)',
            children: 'backend offline — enable ticklist in Settings ▸ Plugins'
          })
        : null
    ]
  })
}


export default {
  id: ID,
  name: 'TickList',
  register(ctx) {
    // host.openWorkspace is the runtime-reopenable pane door: it docks a
    // closeable tile beside the main workspace, the tab's own Close tears it
    // down, and calling it again with the same id FRONTS the existing tab
    // instead of stacking a duplicate. ctx.revealPane/undismissPane are not in
    // this desktop build (verified from the running app), so they can't be the
    // way back — and a plain ctx.register('panes') never re-admits a pane that
    // was closed, which is why the earlier disposer version failed.
    const open = () => {
      if (typeof host.openWorkspace !== 'function') {
        return false
      }
      try {
        host.openWorkspace('ticklist', {
          title: 'ticks',
          // Land in the SAME zone as the terminal pane, as a sibling tab —
          // pos:'center' stacks into the anchor's group (pos:'right' would split
          // a new zone beside it, which is the weird space it kept landing in).
          // enforce replays the placement at boot so it survives re-adoption.
          dock: { pane: 'terminal', pos: 'center', enforce: true },
          // A floor on the tile's width: without it the right-zone sash happily
          // collapses the pane to nothing and the list is unreadable.
          minWidth: '20rem',
          render: () => jsx(TickPane, { ctx })
        })
        return true
      } catch {
        return false
      }
    }

    if (!open()) {
      // Older desktop: fall back to a plain pane; the zone tab strip still has it.
      ctx.register({
        id: 'pane',
        area: 'panes',
        title: 'ticks',
        data: { placement: 'right', width: '360px' },
        render: () => jsx(TickPane, { ctx })
      })
    }

    ctx.register({
      id: 'toggle',
      area: PALETTE_AREA,
      data: {
        id: `${ID}.toggle`,
        label: 'TickList: show checklist',
        keywords: ['tick', 'checklist', 'todo', 'tasks', 'list'],
        run: open
      }
    })
  }
}
