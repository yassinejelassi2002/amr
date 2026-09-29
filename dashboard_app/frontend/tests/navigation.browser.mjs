// Optional browser integration test. Requires Playwright and a running frontend.
// ROS is mocked here: this does not validate ROS, Nav2, physics or Gazebo.
import assert from 'node:assert/strict'
const { chromium } = await import(process.env.AMRX_PLAYWRIGHT_MODULE || 'playwright')
const browser = await chromium.launch({ headless: true,
  ...(process.env.AMRX_BROWSER ? { executablePath: process.env.AMRX_BROWSER } : {}) })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
const errors = []
page.on('pageerror', (error) => errors.push(error.message))
page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()) })
const state = { version: 1, world_id: 'warehouse-harmonic', ready: true, robot_name: 'amr_x',
  phase: 'idle', detail: 'Ready', request_id: '', unavailable_reason: '',
  pose: { x: -1, y: 2, yaw: 0 }, target: null, distance_remaining: null }
let heartbeat = true
let lastRequest
const timers = new Set()
await page.addInitScript(() => {
  localStorage.setItem('currentUser', JSON.stringify({ id: 1, name: 'Navigation test', role: 'admin', status: 'approved' }))
  localStorage.setItem('amrx-map-world', 'warehouse-harmonic')
  localStorage.setItem('amrx-demo', 'false')
})
await page.route((url) => url.pathname.startsWith('/api/'), (route) => route.fulfill({ json: [] }))
await page.routeWebSocket('ws://localhost:9090', (socket) => {
  let subscribed = false
  const publish = () => {
    if (heartbeat && subscribed) socket.send(JSON.stringify({ op: 'publish',
      topic: '/dashboard/navigation/state', msg: { data: JSON.stringify(state) } }))
  }
  const timer = setInterval(publish, 150)
  timers.add(timer)
  socket.onClose(() => { clearInterval(timer); timers.delete(timer) })
  socket.onMessage((raw) => {
    const message = JSON.parse(raw)
    if (message.op === 'subscribe') { subscribed = true; publish() }
    if (message.op === 'unsubscribe') subscribed = false
    if (message.op !== 'call_service') return
    if (message.service.endsWith('/submit')) {
      lastRequest = message.args
      Object.assign(state, { phase: 'navigating', detail: 'Robot navigating to destination',
        request_id: message.args.request_id, target: message.args, distance_remaining: 3.2 })
      socket.send(JSON.stringify({ op: 'service_response', id: message.id,
        service: message.service, result: true, values: { accepted: true, message: 'Received' } }))
      publish()
    } else if (message.service.endsWith('/cancel')) {
      Object.assign(state, { phase: 'canceled', detail: 'Navigation canceled' })
      socket.send(JSON.stringify({ op: 'service_response', id: message.id,
        service: message.service, result: true, values: { success: true, message: 'Canceled' } }))
      publish()
    }
  })
})
async function waitFor(condition, message) {
  for (let i = 0; i < 60; i++) {
    if (await condition()) return
    await new Promise((resolve) => setTimeout(resolve, 100))
  }
  throw new Error(message)
}
try {
  await page.goto(`${process.env.AMRX_TEST_URL || 'http://127.0.0.1:5173'}/map`)
  const panel = page.getByRole('region', { name: 'Gazebo navigation' })
  const go = panel.getByRole('button', { name: 'Go to destination' })
  await waitFor(() => panel.getByRole('button', { name: 'Choose on map' }).isEnabled(), 'Navigation never became ready')
  await panel.getByLabel('X (m)').fill('-2')
  await panel.getByLabel('Y (m)').fill('1')
  await panel.getByLabel('Heading (°)').fill('90')
  await go.click()
  await waitFor(() => !!lastRequest, 'No service request sent')
  assert.equal(lastRequest.world_id, 'warehouse-harmonic')
  assert.equal(lastRequest.x, -2)
  assert.equal(lastRequest.y, 1)
  assert.ok(Math.abs(lastRequest.yaw - Math.PI / 2) < 1e-10)
  await waitFor(() => go.isDisabled(), 'Overlapping goal not blocked')
  await panel.getByRole('button', { name: 'Cancel navigation' }).click()
  await waitFor(() => go.isEnabled(), 'Cancel result not reflected')
  await panel.getByRole('button', { name: 'Choose on map' }).click()
  await page.locator('.map-canvas svg').click({ position: { x: 200, y: 200 } })
  await waitFor(() => panel.getByRole('button', { name: 'Choose on map' }).isVisible(), 'Map picking did not finish')
  assert.ok(Number.isFinite(Number(await panel.getByLabel('X (m)').inputValue())))
  await page.getByRole('button', { name: '3D world', exact: true }).click()
  await waitFor(() => page.locator('.world-robot').count().then((count) => count === 1), 'Missing 3D live robot')
  assert.equal(await page.locator('.world-robot-body').evaluate((element) => getComputedStyle(element).fill), 'rgb(31, 75, 89)')
  heartbeat = false
  await waitFor(() => go.isDisabled(), 'Stale heartbeat did not disable commands')
  await waitFor(() => page.locator('.world-robot').count().then((count) => count === 0), 'Stale robot still shown')
  heartbeat = true
  state.world_id = 'hospital-harmonic'
  await waitFor(() => panel.getByText('Select the simulation world:', { exact: false }).isVisible(), 'World mismatch not detected')
  assert.equal(await go.isDisabled(), true)
  state.world_id = 'warehouse-harmonic'
  await waitFor(() => go.isEnabled(), 'Live data did not recover')
  assert.deepEqual(errors, [])
  if (process.env.AMRX_SCREENSHOT) await page.screenshot({ path: process.env.AMRX_SCREENSHOT, fullPage: true })
  console.log('PASS: ROS service request, radians, cancellation, map selection, 3D marker, stale data and world mismatch; no browser errors.')
} catch (error) {
  console.error('Browser errors:', errors)
  console.error('Page:', await page.locator('body').innerText())
  throw error
} finally {
  for (const timer of timers) clearInterval(timer)
  await browser.close()
}
