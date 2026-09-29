import test from 'node:test'
import assert from 'node:assert/strict'
import { navigationBlockReason, navigationRequestId, parseNavigationState, validateDestination } from '../src/utils/navigation.js'

const state = { version: 1, world_id: 'warehouse-harmonic', ready: true,
  phase: 'idle', detail: 'Ready', request_id: '', pose: { x: -1, y: 2, yaw: 0 } }
const context = { connected: true, fresh: true, state, worldId: state.world_id, demo: false }

test('permits only a connected, ready, matching live simulation', () => {
  assert.equal(navigationBlockReason(context), '')
  for (const change of [{ connected: false }, { fresh: false }, { demo: true },
    { state: null }, { worldId: 'hospital-harmonic' },
    { state: { ...state, ready: false } }]) {
    assert.notEqual(navigationBlockReason({ ...context, ...change }), '')
  }
})

test('blocks overlapping goals through acceptance, navigation and cancellation', () => {
  for (const phase of ['sending', 'navigating', 'canceling']) {
    assert.notEqual(navigationBlockReason({ ...context, state: { ...state, phase } }), '')
  }
  for (const phase of ['succeeded', 'failed', 'rejected', 'canceled']) {
    assert.equal(navigationBlockReason({ ...context, state: { ...state, phase } }), '')
  }
})

test('rejects malformed or incompatible telemetry rather than showing it as live', () => {
  assert.deepEqual(parseNavigationState({ data: JSON.stringify(state) }), state)
  for (const invalid of [{ ...state, version: 2 }, { ...state, ready: 'true' },
    { ...state, phase: 'invented' }, { ...state, pose: { x: null, y: 1, yaw: 0 } }]) {
    assert.throws(() => parseNavigationState({ data: JSON.stringify(invalid) }))
  }
  assert.throws(() => parseNavigationState({ data: 'bad json' }))
})

test('zero and negative coordinates are valid; blank and non-finite goals are not', () => {
  assert.doesNotThrow(() => validateDestination({ x: 0, y: -4, yaw: Math.PI }))
  for (const goal of [null, {}, { x: null, y: 1, yaw: 0 },
    { x: NaN, y: 1, yaw: 0 }, { x: 1, y: Infinity, yaw: 0 }]) {
    assert.throws(() => validateDestination(goal))
  }
})

test('request IDs are unique and usable without secure-context randomUUID', () => {
  const ids = Array.from({ length: 100 }, navigationRequestId)
  assert.equal(new Set(ids).size, ids.length)
  assert.ok(ids.every((id) => /^[a-f0-9]{32}$/.test(id)))
})
