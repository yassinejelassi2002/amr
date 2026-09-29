import { useEffect, useRef, useState } from 'react'
import * as ROSLIB from 'roslib'
import { useRosConnection } from './useRosConnection'
import { ACTIVE_PHASES, STATE_MAX_AGE_MS, navigationBlockReason, navigationRequestId, parseNavigationState, validateDestination } from '../utils/navigation'

export function useNavigation(worldId, demo) {
  const { ros, connected } = useRosConnection()
  const [sample, setSample] = useState(null)
  const [now, setNow] = useState(Date.now)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const callRef = useRef(null)

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 500)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    setSample(null)
    if (!ros || !connected) return
    const topic = new ROSLIB.Topic({ ros, name: '/dashboard/navigation/state',
      messageType: 'std_msgs/msg/String', reconnect_on_close: false })
    const receive = (message) => {
      try {
        setSample({ state: parseNavigationState(message), receivedAt: Date.now() })
      } catch {
        setSample(null)
      }
    }
    topic.subscribe(receive)
    return () => topic.unsubscribe(receive)
  }, [ros, connected])

  useEffect(() => () => {
    if (callRef.current) {
      clearTimeout(callRef.current.timer)
      callRef.current = null
    }
  }, [])

  const state = sample?.state
  const fresh = connected && !!sample && now - sample.receivedAt < STATE_MAX_AGE_MS
  const reason = navigationBlockReason({ connected, fresh, state, worldId, demo })

  function call(name, serviceType, request) {
    if (callRef.current) return
    if (!ros?.isConnected) { setError('ROS disconnected. Request was not sent.'); return }
    setError('')
    setPending(true)
    const token = {}
    const finish = (failure) => {
      if (callRef.current !== token) return
      clearTimeout(token.timer)
      callRef.current = null
      setPending(false)
      if (failure) setError(failure)
    }
    token.timer = setTimeout(() => finish(
      'No acknowledgement received. The robot may still execute the request; check live state before retrying.',
    ), 6000)
    callRef.current = token
    try {
      new ROSLIB.Service({ ros, name, serviceType }).callService(request, (response) => {
        finish((response.accepted ?? response.success) ? '' : response.message || 'Request refused')
      }, (failure) => finish(String(failure)), 5)
    } catch (failure) {
      finish(failure.message)
    }
  }

  function submit(goal) {
    // Recheck wall-clock age at the click, not only at the last render.
    const blocked = navigationBlockReason({ connected,
      fresh: !!sample && Date.now() - sample.receivedAt < STATE_MAX_AGE_MS,
      state, worldId, demo })
    if (blocked) { setError(blocked); return }
    try {
      validateDestination(goal)
      call('/dashboard/navigation/submit', 'navigation_msgs/srv/SubmitNavigationGoal', {
        request_id: navigationRequestId(), world_id: worldId, ...goal,
      })
    } catch (failure) {
      setError(failure.message)
    }
  }

  function cancel() {
    if (demo || !connected || pending) return
    call('/dashboard/navigation/cancel', 'std_srvs/srv/Trigger', {})
  }

  return { state, fresh, connected, reason, pending, error, submit, cancel,
    canCancel: !demo && connected && !pending && (!fresh || ACTIVE_PHASES.has(state?.phase)),
  }
}
