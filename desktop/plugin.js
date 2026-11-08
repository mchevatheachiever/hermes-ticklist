/**
 * TickList — desktop half.
 *
 * A pane of checkboxes. Every tick or untick is posted into the conversation as
 * it happens, so the agent sees the change without being asked. The pane can be
 * collapsed to a header strip, or closed outright and reopened from ⌘K — the
 * disposer `ctx.register` hands back is what makes that reversible.
 *
 * Plain ESM, loaded uncompiled: jsx() calls, no JSX syntax.
 * Only @hermes/plugin-sdk, react and react/jsx-runtime resolve.
 */

import { Button, cn, haptic, host, PALETTE_AREA, useQuery } from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'
import { useCallback, useEffect, useRef, useState } from 'react'

const ID = 'ticklist'

function Row({ item, onToggle, onRemove }) {
  const [busy, setBusy] = useState(false)
  return jsxs('div', {
    className: 'group flex items-start gap-2 rounded px-1 py-1 hover:bg-(--chrome-action-hover)',
    children: [
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
        onClick: () => onRemove(item),
        className:
          'shrink-0 opacity-0 transition-opacity group-hover:opacity-100 text-(--ui-text-quaternary) hover:text-foreground',
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
  const inputRef = useRef(null)

  // Remembered across sessions; the pane state is scratch, this is the setting.
  useEffect(() => {
    let cancelled = false
    try {
      Promise.resolve(ctx.storage.get('removeOnTick'))
        .then((value) => {
          if (!cancelled && value === true) setRemoveOnTick(true)
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
  // unticked first, ticked gathered at the bottom (stable within each group)
  const items = list
    ? [...list.items].sort((a, b) => Number(a.done) - Number(b.done))
    : []
  const done = list ? list.done : 0
  const total = list ? list.total : 0

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
          await ctx.rest(`/items/${encodeURIComponent(item.id)}`, { method: 'DELETE' })
          query.refetch()
          post(`Ticked and removed — ${item.text}`)
          return
        }
        await ctx.rest(`/items/${encodeURIComponent(item.id)}`, {
          method: 'PATCH',
          body: { done: !item.done }
        })
        query.refetch()
        post(`${item.done ? 'Unticked' : 'Ticked'} — ${item.text}`)
      } catch (err) {
        setError(`could not save: ${err && err.message ? err.message : err}`)
      }
    },
    [ctx, post, query, removeOnTick]
  )

  const remove = useCallback(
    async (item) => {
      try {
        await ctx.rest(`/items/${encodeURIComponent(item.id)}`, { method: 'DELETE' })
        query.refetch()
        post(`Removed — ${item.text}`)
      } catch (err) {
        setError(`could not remove: ${err && err.message ? err.message : err}`)
      }
    },
    [ctx, post, query]
  )

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
      query.refetch()
      post(lines.length === 1 ? `Added — ${lines[0]}` : `Added ${lines.length} items`)
    } catch (err) {
      setError(`could not add: ${err && err.message ? err.message : err}`)
    }
  }, [ctx, draft, list, post, query])

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
        onClick: () => setAnnounce((value) => !value),
        title: announce ? 'Ticks are posted to the chat' : 'Ticks stay in the pane',
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
    children: [
      header,

      showTabs
        ? jsx('div', {
            className: 'flex shrink-0 gap-1 overflow-x-auto whitespace-nowrap pb-0.5',
            style: { scrollbarWidth: 'thin' },
            children: state.lists.map((entry) =>
              jsx(
                'button',
                {
                  key: entry.id,
                  type: 'button',
                  onClick: () => setSelected(entry.id),
                  className: cn(
                    'shrink-0 rounded-t border-b-2 px-2 py-1 text-[0.6875rem] transition-colors',
                    entry.id === (list && list.id)
                      ? 'border-(--ui-accent) text-foreground'
                      : 'border-transparent text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover)'
                  ),
                  children: `${entry.name} (${entry.done}/${entry.total})`
                },
                entry.id
              )
            )
          })
        : null,

      jsx('div', {
        className: 'min-h-0 flex-1 overflow-y-auto',
        children: items.length
          ? jsx('div', {
              className: 'flex flex-col gap-0.5',
              children: items.map((item) =>
                jsx(Row, { item, onToggle: toggle, onRemove: remove }, item.id)
              )
            })
          : jsx('div', {
              className: 'p-2 text-center text-[0.6875rem] text-(--ui-text-quaternary)',
              children: list
                ? 'Nothing on the list. Add something below, or ask Hermes.'
                : 'No list yet. Type below, or ask Hermes to make one.'
            })
      }),

      jsxs('div', {
        className: 'flex shrink-0 flex-col gap-1',
        children: [
          jsx('textarea', {
            ref: inputRef,
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
            size: 'xs',
            variant: 'primary',
            onClick: add,
            disabled: !draft.trim(),
            className: 'w-full',
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


function StatusChip({ ctx, onOpen }) {
  const query = useQuery({
    queryKey: ['ticklist', 'chip'],
    queryFn: () => ctx.rest('/lists'),
    refetchInterval: 5000,
    retry: 1
  })
  const lists = (query.data && query.data.lists) || []
  const active = (query.data && query.data.active) || ''
  const list = lists.find((entry) => entry.id === active) || lists[0] || null
  const label = list ? `${list.done}/${list.total}` : '—'

  return jsx('button', {
    type: 'button',
    onClick: () => {
      haptic('tap')
      onOpen()
    },
    title: 'TickList — click to open the pane',
    className:
      'inline-flex h-full items-center gap-1 px-1.5 text-[0.6875rem] transition-colors text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground',
    children: `☑ ${label}`
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
      id: 'chip',
      area: 'statusBar.right',
      order: 128,
      render: () => jsx(StatusChip, { ctx, onOpen: open })
    })

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
