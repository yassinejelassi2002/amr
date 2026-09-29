import { useEffect, useState } from 'react'

export function useRos(url = 'ws://localhost:9090') {
  const [ros, setRos] = useState(null)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    let active = true
    let connection
    let retryTimer

    async function connect() {
      const ROSLIB = await import('roslib')
      if (!active) return

      connection = new ROSLIB.Ros({ url })
      setRos(connection)
      connection.on('connection', () => {
        clearTimeout(retryTimer)
        if (active) setConnected(true)
      })
      connection.on('close', () => {
        if (!active) return
        setConnected(false)
        clearTimeout(retryTimer)
        retryTimer = setTimeout(() => {
          if (active) connection.connect(url)
        }, 2000)
      })
      connection.on('error', () => active && setConnected(false))
    }

    connect()

    return () => {
      active = false
      clearTimeout(retryTimer)
      connection?.close()
    }
  }, [url])

  return { ros, connected }
}
