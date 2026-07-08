import React, { useEffect, useState, useCallback, useRef } from 'react'
import { intelligence } from '../../lib/api'
import { MonitorEngineContext, type MonitorState } from './monitorEngineContext'

/**
 * World Monitor Intelligence Engine Context
 * Ported from App.ts and DataLoaderManager.ts in worldmonitor-main
 */

export const MonitorProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, setState] = useState<MonitorState>({
    feeds: [],
    flights: [],
    vessels: [],
    satellites: [],
    ciiScores: [],
    tensions: {},
    cables: [],
    isGlobalLoading: false,
    lastUpdate: null,
  })

  const refreshIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const refreshAll = useCallback(async () => {
    setState(prev => ({ ...prev, isGlobalLoading: true }))
    try {
      const [maritime, flightsResp, sats, cii, tensions, cables] = await Promise.all([
        intelligence.maritime.signals(),
        intelligence.aviation.military(),
        intelligence.satellites.tle(),
        intelligence.cii.scores(),
        intelligence.gdelt.tensions(),
        intelligence.infrastructure.cables(),
      ])

      setState({
        feeds: [],
        flights: (flightsResp as { flights?: unknown[] })?.flights || [],
        vessels: (maritime as { events?: unknown[] })?.events || [],
        satellites: (sats as unknown[]) || [],
        ciiScores: (cii as { cii?: unknown[] })?.cii || [],
        tensions: (tensions as { scores?: Record<string, number> })?.scores || {},
        cables: (cables as { advisories?: unknown[] })?.advisories || [],
        isGlobalLoading: false,
        lastUpdate: new Date(),
      })
    } catch (error) {
      console.error('[MonitorEngine] Failed to hydrate intelligence streams:', error)
      setState(prev => ({ ...prev, isGlobalLoading: false }))
    }
  }, [])

  const updateCII = useCallback(async () => {
    try {
      const cii = await intelligence.cii.scores()
      setState(prev => ({ ...prev, ciiScores: (cii as { cii?: unknown[] })?.cii || [] }))
    } catch (error) {
      console.error('[MonitorEngine] Failed to update CII indexes:', error)
    }
  }, [])

  useEffect(() => {
    const boot = window.setTimeout(() => {
      void refreshAll()
    }, 0)
    const interval = setInterval(() => {
      void refreshAll()
    }, 5 * 60 * 1000)

    refreshIntervalRef.current = interval
    return () => {
      clearTimeout(boot)
      clearInterval(interval)
    }
  }, [refreshAll])

  return (
    <MonitorEngineContext.Provider value={{ state, refreshAll, updateCII }}>
      {children}
    </MonitorEngineContext.Provider>
  )
}
