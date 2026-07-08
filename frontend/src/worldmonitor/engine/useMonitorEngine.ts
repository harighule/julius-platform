import { useContext } from 'react'
import { MonitorEngineContext } from './monitorEngineContext'

export function useMonitorEngine() {
  const ctx = useContext(MonitorEngineContext)
  if (!ctx) throw new Error('useMonitorEngine must be used within MonitorProvider')
  return ctx
}
