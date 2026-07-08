import { useEffect, useRef, useState, memo } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { type GlobeEvent, CATEGORY_CONFIG } from '../lib/globeData'

interface Props {
  className?: string
  events: GlobeEvent[]
  onEventClick?: (ev: GlobeEvent) => void
  activeView?: string // 'global', 'americas', 'europe', 'mena', 'asia', 'africa'
}

type CustomMarker = maplibregl.Marker & { 
  eventId: string
  getElement: () => HTMLElement
}

const VIEW_PRESETS: Record<string, { center: [number, number]; zoom: number }> = {
  global: { center: [0, 20], zoom: 1.5 },
  americas: { center: [-95, 35], zoom: 2.5 },
  europe: { center: [15, 50], zoom: 3.5 },
  mena: { center: [40, 25], zoom: 3.5 },
  asia: { center: [100, 30], zoom: 3 },
  africa: { center: [20, 0], zoom: 3 },
}

export const MonitorMap2D = memo(function MonitorMap2D({ className = '', events, onEventClick, activeView = 'global' }: Props) {
  const mapContainer = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const markersRef = useRef<Map<string, CustomMarker>>(new Map())
  const [mapLoaded, setMapLoaded] = useState(false)

  useEffect(() => {
    if (!mapContainer.current) return

    // Protomaps/OpenFreeMap style (free, no API key needed, dark theme)
    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: 'https://tiles.openfreemap.org/styles/liberty', // A reliable free vector tile style
      center: VIEW_PRESETS.global.center,
      zoom: VIEW_PRESETS.global.center[1], // wait, zoom is zoom
    })

    // Override the zoom which was set incorrectly above initially if I didn't fix it
    map.setZoom(VIEW_PRESETS.global.zoom)

    // Add navigation controls
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right')

    // Optional: Make the base map stark dark and blueish via CSS filter rather than complex custom style JSON
    mapContainer.current.style.filter = 'invert(100%) hue-rotate(180deg) brightness(90%) contrast(120%)'
    
    map.on('load', () => {
      setMapLoaded(true)
    })

    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
      setMapLoaded(false)
    }
  }, [])

  // Handle View Transitions
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapLoaded) return

    const preset = VIEW_PRESETS[activeView] || VIEW_PRESETS.global
    map.flyTo({
      center: preset.center,
      zoom: preset.zoom,
      speed: 1.2,
      curve: 1.5,
    })
  }, [activeView, mapLoaded])

  // Map events to markers
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapLoaded) return

    const currentMarkers = markersRef.current
    const newEventsMap = new Map(events.map(e => [e.id, e]))
    const idsToRemove: string[] = []

    // Remove old markers
    for (const [id, marker] of currentMarkers.entries()) {
      if (!newEventsMap.has(id)) {
        marker.remove()
        idsToRemove.push(id)
      }
    }
    idsToRemove.forEach(id => currentMarkers.delete(id))

    // Add or update markers
    events.forEach(ev => {
      if (currentMarkers.has(ev.id)) return // Already exists
      
      const el = document.createElement('div')
      const config = CATEGORY_CONFIG[ev.category] || { color: '#ffffff', emoji: '📍' }
      
      // Determine size based on severity
      let sizeClass = 'w-4 h-4 text-[10px]'
      let pulseHtml = ''
      if (ev.severity === 'critical') {
        sizeClass = 'w-6 h-6 text-sm'
        pulseHtml = `<div class="absolute inset-0 rounded-full animate-ping opacity-50" style="background-color: ${config.color}"></div>`
      } else if (ev.severity === 'high') {
        sizeClass = 'w-5 h-5 text-xs'
        pulseHtml = `<div class="absolute inset-0 rounded-full animate-ping opacity-30" style="background-color: ${config.color}"></div>`
      }

      el.className = `relative flex items-center justify-center rounded-full cursor-pointer transition-transform hover:scale-125 z-10 ${sizeClass}`
      el.style.backgroundColor = config.color + '44' // Transparent background
      el.style.border = `1px solid ${config.color}`
      el.style.boxShadow = `0 0 10px ${config.color}`
      
      // Revert the invert filter just for the marker icon since the whole map is inverted
      el.innerHTML = `
        ${pulseHtml}
        <span style="filter: invert(100%) hue-rotate(180deg);" class="z-10 drop-shadow-md">${config.emoji}</span>
      `

      // Click handler
      el.addEventListener('click', (e) => {
        e.stopPropagation()
        onEventClick?.(ev)
      })

      // Add popup on hover
      const popup = new maplibregl.Popup({
        closeButton: false,
        closeOnClick: false,
        offset: 15,
        className: 'monitor-map-popup' // Will style via CSS or just relies on maplibre defaults overridden
      })
      
      const popupContent = `
        <div style="filter: invert(100%) hue-rotate(180deg); padding: 4px;">
          <div style="font-size: 11px; font-weight: bold; color: ${config.color}; font-family: monospace;">${ev.title}</div>
          <div style="font-size: 9px; margin-top: 2px; opacity: 0.8; font-family: monospace;">${ev.description?.substring(0, 50)}${ev.description && ev.description.length > 50 ? '...' : ''}</div>
          <div style="font-size: 8px; margin-top: 4px; opacity: 0.6; font-family: monospace;">[LAT: ${ev.lat.toFixed(3)}, LNG: ${ev.lng.toFixed(3)}]</div>
        </div>
      `
      
      el.addEventListener('mouseenter', () => {
        popup.setLngLat([ev.lng, ev.lat]).setHTML(popupContent).addTo(map)
      })
      el.addEventListener('mouseleave', () => {
        popup.remove()
      })

      // Fix coordinate ordering! MapLibre uses [lng, lat]
      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([ev.lng, ev.lat])
        .addTo(map)

      ;(marker as CustomMarker).eventId = ev.id
      currentMarkers.set(ev.id, marker as CustomMarker)
    })
  }, [events, mapLoaded, onEventClick])

  return (
    <div className={`w-full h-full relative ${className}`}>
      <div ref={mapContainer} className="w-full h-full" />
      {/* Target Crosshairs purely aesthetic */}
      <div className="absolute inset-0 pointer-events-none flex items-center justify-center opacity-10">
        <svg width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
          <line x1="50%" y1="0" x2="50%" y2="100%" stroke="var(--color-julius-accent)" strokeWidth="1" strokeDasharray="5,15" />
          <line x1="0" y1="50%" x2="100%" y2="50%" stroke="var(--color-julius-accent)" strokeWidth="1" strokeDasharray="5,15" />
          <circle cx="50%" cy="50%" r="150" fill="none" stroke="var(--color-julius-accent)" strokeWidth="1" strokeDasharray="2,8" />
        </svg>
      </div>
    </div>
  )
})
