export const ACTIVE_PHASES = new Set(['sending', 'navigating', 'canceling'])
export const STATE_MAX_AGE_MS = 2500

export function navigationRequestId() {
  // getRandomValues also works on a plain HTTP LAN dashboard.
  return Array.from(crypto.getRandomValues(new Uint8Array(16)),
    (byte) => byte.toString(16).padStart(2, '0')).join('')
}

export function parseNavigationState(message) {
  const state = JSON.parse(message.data)
  const phases = ['idle', ...ACTIVE_PHASES, 'succeeded', 'canceled', 'failed', 'rejected']
  if (state.version !== 1 || typeof state.world_id !== 'string'
    || typeof state.ready !== 'boolean' || !phases.includes(state.phase)
    || typeof state.detail !== 'string' || typeof state.request_id !== 'string') {
    throw new Error('Unsupported navigation state')
  }
  if (state.pose && ![state.pose.x, state.pose.y, state.pose.yaw].every(Number.isFinite)) {
    throw new Error('Invalid robot pose')
  }
  return state
}

export function navigationBlockReason({ connected, fresh, state, worldId, demo }) {
  if (demo) return 'Demo mode: navigation commands are disabled.'
  if (!connected) return 'ROS disconnected. Check Robot connection in Settings.'
  if (!fresh || !state) return 'Waiting for live navigation state. Simulation may be paused or disconnected.'
  if (state.world_id !== worldId) return `Select the simulation world: ${state.world_id || 'not configured'}.`
  if (!state.ready) return state.unavailable_reason || 'Navigation is not ready.'
  if (ACTIVE_PHASES.has(state.phase)) return 'A destination is active. Wait for completion or cancel it.'
  return ''
}

export function validateDestination(goal) {
  if (!goal || ![goal.x, goal.y, goal.yaw].every(Number.isFinite)) {
    throw new Error('Choose a destination with finite coordinates.')
  }
}
