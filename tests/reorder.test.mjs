/**
 * The reorder arithmetic, tested outside the app.
 *
 * `desktop/plugin.js` cannot import a sibling module — only `@hermes/plugin-sdk`,
 * `react` and `react/jsx-runtime` resolve inside the app — so the two pure
 * functions live in that file and this test reads them back out by name and
 * evaluates them. Ugly, but the alternative is no coverage for the logic that
 * has now shipped two bugs: an index computed from a stale array, and a
 * `splice(start, deleteCount, item)` call that deleted the neighbour.
 *
 *   node --test tests/reorder.test.mjs
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import test from 'node:test'
import assert from 'node:assert/strict'

const here = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(here, '..', 'desktop', 'plugin.js'), 'utf8')

/** Pull `function name(...) { ... }` out of the plugin source, by brace depth. */
function extract(name) {
  const start = source.indexOf(`function ${name}(`)
  assert.notEqual(start, -1, `${name} not found in plugin.js`)
  const open = source.indexOf('{', start)
  let depth = 0
  for (let i = open; i < source.length; i += 1) {
    if (source[i] === '{') depth += 1
    if (source[i] === '}') {
      depth -= 1
      if (depth === 0) return source.slice(start, i + 1)
    }
  }
  throw new Error(`${name} has unbalanced braces`)
}

// eslint-disable-next-line no-new-func
const { applyMove, applySwap } = new Function(
  `${extract('applyMove')}\n${extract('applySwap')}\nreturn { applyMove, applySwap }`
)()

const ORDER = ['a', 'b', 'c', 'd']

test('applyMove lands after the target when asked', () => {
  assert.deepEqual(applyMove(ORDER, 'a', 'b', true), ['b', 'a', 'c', 'd'])
})

test('applyMove reaches the last slot', () => {
  assert.deepEqual(applyMove(ORDER, 'a', 'd', true), ['b', 'c', 'd', 'a'])
})

test('applyMove lands before the target when asked', () => {
  assert.deepEqual(applyMove(ORDER, 'd', 'a', false), ['d', 'a', 'b', 'c'])
  assert.deepEqual(applyMove(ORDER, 'a', 'c', false), ['b', 'a', 'c', 'd'])
})

test('applyMove is a no-op for the same row', () => {
  assert.deepEqual(applyMove(ORDER, 'b', 'b', true), ORDER)
})

test('applyMove ignores ids that are not there', () => {
  assert.deepEqual(applyMove(ORDER, 'zz', 'a', true), ORDER)
  assert.deepEqual(applyMove(ORDER, 'a', 'zz', true), ORDER)
})

test('applyMove never loses or duplicates a row', () => {
  // This is the shape of the bug that shipped: a splice with the wrong second
  // argument silently dropped an item, and the server re-appended it at the end.
  for (const from of ORDER) {
    for (const to of ORDER) {
      for (const after of [true, false]) {
        const out = applyMove(ORDER, from, to, after)
        assert.equal(out.length, ORDER.length, `${from}->${to} after=${after} changed length`)
        assert.deepEqual([...out].sort(), [...ORDER].sort(), `${from}->${to} lost a row`)
      }
    }
  }
})

test('applySwap exchanges two neighbours, both directions', () => {
  assert.deepEqual(applySwap(ORDER, 'a', 'b'), ['b', 'a', 'c', 'd'])
  assert.deepEqual(applySwap(ORDER, 'c', 'b'), ['a', 'c', 'b', 'd'])
  assert.deepEqual(applySwap(ORDER, 'd', 'a'), ['d', 'b', 'c', 'a'])
})

test('applySwap keeps the array intact', () => {
  const out = applySwap(ORDER, 'b', 'c')
  assert.equal(out.length, ORDER.length)
  assert.deepEqual([...out].sort(), [...ORDER].sort())
})

test('applySwap ignores unknown ids', () => {
  assert.deepEqual(applySwap(ORDER, 'b', 'zz'), ORDER)
})

test('neither helper mutates the caller array', () => {
  const input = [...ORDER]
  applyMove(input, 'a', 'd', true)
  applySwap(input, 'a', 'b')
  assert.deepEqual(input, ORDER)
})
