import './NavigationPanel.css'

const LABELS = { idle: 'Ready', sending: 'Sending', navigating: 'Navigating',
  canceling: 'Canceling', succeeded: 'Destination reached', canceled: 'Canceled',
  failed: 'Failed', rejected: 'Rejected' }

export default function NavigationPanel({ navigation, goal, setGoal, picking, setPicking }) {
  const { state, fresh, reason, pending, error, submit, cancel, canCancel } = navigation
  return (
    <section className="navigation-panel" aria-label="Gazebo navigation">
      <div>
        <strong>Gazebo navigation · AMR-X</strong>
        <p role="status" aria-live="polite">
          {fresh ? LABELS[state.phase] : 'Live state unavailable'}
          {fresh && state.detail ? ` — ${state.detail}` : ''}
        </p>
        {reason && <p>{reason}</p>}
        {fresh && ['sending', 'navigating', 'canceling'].includes(state.phase)
          && Number.isFinite(state.distance_remaining) && <p>Remaining: {state.distance_remaining.toFixed(2)} m</p>}
      </div>
      <form onSubmit={(event) => { event.preventDefault(); submit(goal) }}>
        <button type="button" disabled={pending || !!reason} aria-pressed={picking}
          onClick={() => setPicking(!picking)}>{picking ? 'Click the 2D map…' : 'Choose on map'}</button>
        {['x', 'y', 'yaw'].map((key) => (
          <label key={key}>
            {key === 'yaw' ? 'Heading (°)' : `${key.toUpperCase()} (m)`}
            <input type="number" step="any" required
              value={goal?.[key] == null ? '' : key === 'yaw' ? goal.yaw * 180 / Math.PI : goal[key]}
              onChange={(event) => {
                const value = event.target.value === '' ? null : Number(event.target.value)
                setGoal({ yaw: 0, ...goal, [key]: value == null ? null : key === 'yaw' ? value * Math.PI / 180 : value })
              }} />
          </label>
        ))}
        <button type="submit" disabled={pending || !!reason || !goal}>Go to destination</button>
        <button type="button" disabled={!canCancel} onClick={cancel}>Cancel navigation</button>
      </form>
      {pending && <p role="status">Waiting for acknowledgement…</p>}
      {error && <p role="alert" className="navigation-error">{error}</p>}
      <small>Closing this page does not cancel navigation. Use Cancel navigation before leaving.</small>
    </section>
  )
}
