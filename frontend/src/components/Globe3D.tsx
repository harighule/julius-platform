import { useEffect, useRef, useState, memo, useMemo } from 'react'
import Globe from 'react-globe.gl'
import * as THREE from 'three'
import { type GlobeEvent, CATEGORY_CONFIG } from '../lib/globeData'

interface Props {
  className?: string
  onGeoChange?: (c: { lat: number; lng: number } | null) => void
  events?: GlobeEvent[]
  onEventClick?: (event: GlobeEvent) => void
}

export const Globe3D = memo(function Globe3D({ className = '', onGeoChange, events = [], onEventClick }: Props) {
  const globeEl = useRef<any>(null)
  const wrapperRef = useRef<HTMLDivElement>(null)
  const [dimensions, setDimensions] = useState({ width: 800, height: 800 })
  const [isDragging, setIsDragging] = useState(false)
  const lastGeo = useRef<{ lat: number; lng: number } | null>(null)



  // Resize observer
  useEffect(() => {
    const el = wrapperRef.current
    if (!el) return
    const ro = new ResizeObserver(() => {
      setDimensions({ width: el.clientWidth, height: el.clientHeight })
    })
    ro.observe(el)
    setDimensions({ width: el.clientWidth, height: el.clientHeight })
    return () => ro.disconnect()
  }, [])

  // Orbit controls + scene lighting + material tweaks
  useEffect(() => {
    if (!globeEl.current) return
    const ctrl = globeEl.current.controls()
    ctrl.autoRotate = true
    ctrl.autoRotateSpeed = 0.3
    ctrl.enableZoom = true
    ctrl.enablePan = false
    ctrl.minDistance = 110
    ctrl.maxDistance = 900
    globeEl.current.pointOfView({ altitude: 1.8 })

    // Soft balanced lighting — not too bright so texture shows through
    const ambient = new THREE.AmbientLight(0xddeeff, 0.6)
    const sun = new THREE.DirectionalLight(0xffffff, 0.9)
    sun.position.set(200, 100, 300)
    globeEl.current.lights([ambient, sun])

    // After the texture loads (~1s), tweak the library's own material
    // to add subtle specular/metalness depth without wiping the texture
    const timer = setTimeout(() => {
      const scene = globeEl.current?.scene()
      if (!scene) return
      scene.traverse((obj: THREE.Object3D) => {
        if (obj instanceof THREE.Mesh && obj.geometry instanceof THREE.SphereGeometry) {
          const params = (obj.geometry as THREE.SphereGeometry).parameters
          if (params && params.radius > 50) {
            // This is the globe surface mesh — tweak its material
            const mat = obj.material as THREE.MeshStandardMaterial
            if (mat && 'roughness' in mat) {
              mat.roughness = 0.7   // Slightly glossy oceans
              mat.metalness = 0.05  // Subtle reflective sheen
              mat.needsUpdate = true
            }
          }
        }
      })
    }, 1500)
    return () => clearTimeout(timer)
  }, [])

  // Raycasting for geo coords
  useEffect(() => {
    const wrapper = wrapperRef.current
    if (!wrapper || !onGeoChange) return
    const onMove = (e: PointerEvent) => {
      if (!globeEl.current) return
      const rect = wrapper.getBoundingClientRect()
      if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) {
        if (lastGeo.current) { lastGeo.current = null; onGeoChange(null) }
        return
      }
      const x = e.clientX - rect.left
      const y = e.clientY - rect.top
      const camera = globeEl.current.camera()
      const scene = globeEl.current.scene()
      if (!camera || !scene) return
      const raycaster = new THREE.Raycaster()
      raycaster.setFromCamera(new THREE.Vector2((x / rect.width) * 2 - 1, -(y / rect.height) * 2 + 1), camera)

      // Find ONLY the main globe sphere (the largest SphereGeometry, radius ≥ 50).
      // This excludes the atmosphere halo, point markers, and ring meshes which
      // are all smaller spheres but still SphereGeometry — causing false positives.
      let globeMesh: THREE.Mesh | null = null
      let maxRadius = 0
      scene.traverse((obj: THREE.Object3D) => {
        if (obj instanceof THREE.Mesh && obj.geometry instanceof THREE.SphereGeometry) {
          const params = (obj.geometry as THREE.SphereGeometry).parameters
          if (params && params.radius > maxRadius) {
            maxRadius = params.radius
            globeMesh = obj
          }
        }
      })

      if (!globeMesh || maxRadius < 50) {
        // Globe mesh not found or too small — clear coords
        if (lastGeo.current) { lastGeo.current = null; onGeoChange(null) }
        return
      }

      const hits = raycaster.intersectObject(globeMesh, false)
      if (hits.length > 0) {
        const coords = globeEl.current.toGeoCoords(hits[0].point)
        if (coords && !isNaN(coords.lat) && !isNaN(coords.lng)) {
          lastGeo.current = coords
          onGeoChange(coords)
          return
        }
      }
      // Cursor is over background / space — clear coords
      if (lastGeo.current) { lastGeo.current = null; onGeoChange(null) }
    }
    wrapper.addEventListener('pointermove', onMove, { passive: true })
    return () => wrapper.removeEventListener('pointermove', onMove)
  }, [onGeoChange])

  // Prepare ring pulse data (critical/high events get expanding rings)
  const ringsData = useMemo(() =>
    events
      .filter(e => e.severity === 'critical' || e.severity === 'high')
      .map(e => ({
        lat: e.lat,
        lng: e.lng,
        maxR: e.severity === 'critical' ? 4 : 2.5,
        propagationSpeed: e.severity === 'critical' ? 2 : 1.2,
        repeatPeriod: e.severity === 'critical' ? 700 : 1000,
        color: CATEGORY_CONFIG[e.category]?.color || '#ffffff',
        event: e,
      })),
    [events]
  )

  // Point data for all events
  const pointsData = useMemo(() =>
    events.map(e => ({
      lat: e.lat,
      lng: e.lng,
      size: e.severity === 'critical' ? 0.55 : e.severity === 'high' ? 0.42 : e.severity === 'medium' ? 0.30 : 0.22,
      color: CATEGORY_CONFIG[e.category]?.color || '#ffffff',
      event: e,
    })),
    [events]
  )

  const GlobeComponent = (Globe as any).default || Globe

  return (
    <div
      ref={wrapperRef}
      className={`globe-container w-full h-full flex items-center justify-center select-none ${className}`}
      style={{ cursor: isDragging ? 'grabbing' : 'grab' }}
      onMouseDown={() => setIsDragging(true)}
      onMouseUp={() => setIsDragging(false)}
      onMouseLeave={() => { setIsDragging(false); onGeoChange?.(null) }}
    >
      <GlobeComponent
        ref={globeEl}
        width={dimensions.width}
        height={dimensions.height}

        // Hacking / Midnight textures
        globeImageUrl="//unpkg.com/three-globe/example/img/earth-night.jpg"
        bumpImageUrl="//unpkg.com/three-globe/example/img/earth-topology.png"
        backgroundImageUrl="" // Keep background black

        // Graticule grid lines like a radar HUD
        showGraticules={true}
        atmosphereColor="#00d4ff"
        atmosphereAltitude={0.15}
        showAtmosphere={true}
        showPointerCursor={false}

        // ── Event Points ──────────────────────────────────────────────
        pointsData={pointsData}
        pointLat={(d: any) => d.lat}
        pointLng={(d: any) => d.lng}
        pointRadius={(d: any) => d.size}
        pointColor={(d: any) => d.color}
        pointAltitude={0.005}
        pointResolution={8}
        onPointClick={(d: any) => { onEventClick?.(d.event); globeEl.current?.controls()?.update() }}

        // ── Expanding Ring Pulses (critical/high only) ─────────────────
        ringsData={ringsData}
        ringLat={(d: any) => d.lat}
        ringLng={(d: any) => d.lng}
        ringMaxRadius={(d: any) => d.maxR}
        ringPropagationSpeed={(d: any) => d.propagationSpeed}
        ringRepeatPeriod={(d: any) => d.repeatPeriod}
        ringColor={(d: any) => (t: number) => `${d.color}${Math.round((1 - t) * 255).toString(16).padStart(2, '0')}`}
        ringAltitude={0.001}
      />
    </div>
  )
})
