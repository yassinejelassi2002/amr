import { useEffect, useState } from 'react'
import { useRos } from '../hooks/useRos'
import { RosContext } from './internalContexts'

const DEFAULT_ROSBRIDGE_URL = 'ws://localhost:9090'
const STORAGE_KEY = 'amrx-ws-url'

function readRosbridgeUrl() {
  try {
    return localStorage.getItem(STORAGE_KEY) || DEFAULT_ROSBRIDGE_URL
  } catch {
    return DEFAULT_ROSBRIDGE_URL
  }
}

export function RosProvider({ children }) {
  const [url, setUrl] = useState(readRosbridgeUrl)
  useEffect(() => {
    const update = () => setUrl(readRosbridgeUrl())
    window.addEventListener('amrx-ros-url-changed', update)
    window.addEventListener('storage', update)
    return () => {
      window.removeEventListener('amrx-ros-url-changed', update)
      window.removeEventListener('storage', update)
    }
  }, [])
  const connection = useRos(url)

  return (
    <RosContext.Provider value={{ ...connection, url }}>
      {children}
    </RosContext.Provider>
  )
}
