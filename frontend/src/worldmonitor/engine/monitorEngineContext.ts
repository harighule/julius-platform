import { createContext } from 'react'

export interface MonitorState {
  feeds: unknown[]
  flights: unknown[]
  vessels: unknown[]
  satellites: unknown[]
  ciiScores: unknown[]
  tensions: Record<string, number>
  cables: unknown[]
  isGlobalLoading: boolean
  lastUpdate: Date | null
}

export interface MonitorEngineContextValue {
  state: MonitorState
  refreshAll: () => Promise<void>
  updateCII: () => Promise<void>
}

export const MonitorEngineContext = createContext<MonitorEngineContextValue | undefined>(undefined)
