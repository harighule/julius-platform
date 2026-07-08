import { useState, useMemo, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { jsPDF } from 'jspdf'
import autoTable from 'jspdf-autotable'
import { osint } from '../lib/api'
import { fetchGlobeEvents, type GlobeEvent, CATEGORY_CONFIG } from '../lib/globeData'

// ─── Country name mapping ─────────────────────────────────────────────────────
const COUNTRY_NAMES: Record<string, string> = {
  AF:'Afghanistan',AL:'Albania',DZ:'Algeria',AR:'Argentina',AM:'Armenia',AU:'Australia',AT:'Austria',
  AZ:'Azerbaijan',BH:'Bahrain',BD:'Bangladesh',BY:'Belarus',BE:'Belgium',BR:'Brazil',BG:'Bulgaria',
  CA:'Canada',CL:'Chile',CN:'China',CO:'Colombia',HR:'Croatia',CZ:'Czech Republic',DK:'Denmark',
  EG:'Egypt',EE:'Estonia',FI:'Finland',FR:'France',GE:'Georgia',DE:'Germany',GH:'Ghana',
  GR:'Greece',HK:'Hong Kong',HU:'Hungary',IN:'India',ID:'Indonesia',IR:'Iran',IQ:'Iraq',
  IE:'Ireland',IL:'Israel',IT:'Italy',JP:'Japan',JO:'Jordan',KZ:'Kazakhstan',KE:'Kenya',
  KP:'North Korea',KR:'South Korea',KW:'Kuwait',LV:'Latvia',LB:'Lebanon',LT:'Lithuania',
  LU:'Luxembourg',MY:'Malaysia',MX:'Mexico',MD:'Moldova',MA:'Morocco',NL:'Netherlands',
  NZ:'New Zealand',NG:'Nigeria',NO:'Norway',PK:'Pakistan',PS:'Palestine',PE:'Peru',
  PH:'Philippines',PL:'Poland',PT:'Portugal',QA:'Qatar',RO:'Romania',RU:'Russia',
  SA:'Saudi Arabia',SG:'Singapore',SK:'Slovakia',SI:'Slovenia',ZA:'South Africa',ES:'Spain',
  SE:'Sweden',CH:'Switzerland',SY:'Syria',TW:'Taiwan',TH:'Thailand',TN:'Tunisia',TR:'Turkey',
  UA:'Ukraine',AE:'UAE',GB:'United Kingdom',US:'United States',UZ:'Uzbekistan',
  VN:'Vietnam',YE:'Yemen',ZW:'Zimbabwe',
}
function countryName(code: string): string {
  if (!code) return ''
  return COUNTRY_NAMES[code.toUpperCase()] || code.toUpperCase()
}

// ─── Region mapping ───────────────────────────────────────────────────────────
const COUNTRY_TO_REGION: Record<string, string> = {
  US:'North America',CA:'North America',MX:'North America',
  GB:'Europe',DE:'Europe',FR:'Europe',IT:'Europe',ES:'Europe',PT:'Europe',NL:'Europe',
  BE:'Europe',AT:'Europe',CH:'Europe',SE:'Europe',NO:'Europe',DK:'Europe',FI:'Europe',
  PL:'Europe',CZ:'Europe',SK:'Europe',HU:'Europe',RO:'Europe',BG:'Europe',GR:'Europe',
  IE:'Europe',LU:'Europe',EE:'Europe',LV:'Europe',LT:'Europe',HR:'Europe',SI:'Europe',
  AL:'Europe',BY:'Europe',MD:'Europe',UA:'Europe',GE:'Europe',AM:'Europe',AZ:'Europe',
  IR:'Middle East',IQ:'Middle East',SY:'Middle East',JO:'Middle East',LB:'Middle East',
  IL:'Middle East',PS:'Middle East',SA:'Middle East',AE:'Middle East',QA:'Middle East',
  KW:'Middle East',BH:'Middle East',YE:'Middle East',TR:'Middle East',
  CN:'Asia-Pacific',JP:'Asia-Pacific',KR:'Asia-Pacific',KP:'Asia-Pacific',TW:'Asia-Pacific',
  IN:'Asia-Pacific',PK:'Asia-Pacific',BD:'Asia-Pacific',TH:'Asia-Pacific',VN:'Asia-Pacific',
  PH:'Asia-Pacific',MY:'Asia-Pacific',SG:'Asia-Pacific',ID:'Asia-Pacific',HK:'Asia-Pacific',
  AU:'Asia-Pacific',NZ:'Asia-Pacific',KZ:'Asia-Pacific',UZ:'Asia-Pacific',
  BR:'South America',AR:'South America',CL:'South America',CO:'South America',PE:'South America',
  EG:'Africa',NG:'Africa',ZA:'Africa',KE:'Africa',GH:'Africa',TN:'Africa',DZ:'Africa',
  MA:'Africa',ZW:'Africa',
  RU:'Russia & CIS',
}
const ALL_REGIONS = ['All Regions','North America','Europe','Middle East','Asia-Pacific','South America','Africa','Russia & CIS']

type TabKey = 'cyber' | 'intelligence'

interface CyberThreatFeed {
  id?: string | number
  ip: string
  source: string
  country?: string
  tags: string[]
  details?: string
  risk_level: string
  last_seen?: string
}

export function ThreatFeedsPanel() {
  const [tab, setTab] = useState<TabKey>('intelligence')
  const [search, setSearch] = useState('')
  const [filterRisk, setFilterRisk] = useState('All')
  const [filterSource, setFilterSource] = useState('All')
  const [filterCountry, setFilterCountry] = useState('All Countries')
  const [filterRegion, setFilterRegion] = useState('All Regions')

  // Globe intelligence events
  const [globeEvents, setGlobeEvents] = useState<GlobeEvent[]>([])
  useEffect(() => {
    const allLayers = new Set(['conflict','hotspot','base','nuclear','natural','cyber'])
    fetchGlobeEvents(allLayers).then(setGlobeEvents)
    const interval = setInterval(() => fetchGlobeEvents(allLayers).then(setGlobeEvents), 3 * 60_000)
    return () => clearInterval(interval)
  }, [])

  // Cyber feeds
  const { data, isLoading, error, dataUpdatedAt } = useQuery({
    queryKey: ['threat-feeds'],
    queryFn: osint.threatFeeds,
    refetchInterval: 60000,
    staleTime: 50000,
  })

  const feeds = useMemo((): CyberThreatFeed[] => {
    const raw = (data as { data?: unknown } | undefined)?.data
    if (!Array.isArray(raw)) return []
    return raw as CyberThreatFeed[]
  }, [data])
  const sourceSummary = (data as { sources?: Record<string, number> } | undefined)?.sources ?? {}
  const sources = ['All', ...Array.from(new Set(feeds.map(f => f.source)))]
  const risks = ['All', 'Critical', 'High', 'Medium', 'Low']

  const availableCountries = useMemo(() => {
    const codes = new Set<string>()
    feeds.forEach((f) => { if (f.country) codes.add(f.country.toUpperCase()) })
    const sorted = Array.from(codes).sort((a, b) => countryName(a).localeCompare(countryName(b)))
    return ['All Countries', ...sorted]
  }, [feeds])

  const filteredFeeds = useMemo(() => {
    return feeds.filter((f: CyberThreatFeed) => {
      const q = search.toLowerCase()
      const matchesSearch = !q || f.ip.includes(q) || f.tags.some((t: string) => t.includes(q)) ||
        (f.details || '').toLowerCase().includes(q) || countryName(f.country || '').toLowerCase().includes(q)
      const matchesRisk = filterRisk === 'All' || f.risk_level === filterRisk
      const matchesSource = filterSource === 'All' || f.source === filterSource
      const cc = (f.country || '').toUpperCase()
      const matchesCountry = filterCountry === 'All Countries' || cc === filterCountry
      const region = COUNTRY_TO_REGION[cc] || 'Unknown'
      const matchesRegion = filterRegion === 'All Regions' || region === filterRegion
      return matchesSearch && matchesRisk && matchesSource && matchesCountry && matchesRegion
    })
  }, [feeds, search, filterRisk, filterSource, filterCountry, filterRegion])

  // Filter globe events
  const filteredGlobeEvents = useMemo(() => {
    return globeEvents.filter(e => {
      const q = search.toLowerCase()
      const matchesSearch = !q || e.title.toLowerCase().includes(q) || e.description.toLowerCase().includes(q) ||
        (e.country || '').toLowerCase().includes(q)
      return matchesSearch
    })
  }, [globeEvents, search])

  const lastUpdated = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : '—'

  // ── PDF Export ─────────────────────────────────────────────────────────────
  // Helper: Strip emoji and special unicode characters, keep only ASCII and basic Latin
  const stripEmoji = (text: string): string => {
    return text
      .replace(/[\u{1F300}-\u{1F9FF}]/gu, '') // Emoji ranges
      .replace(/[\u{2600}-\u{27BF}]/gu, '')   // Miscellaneous symbols
      .replace(/[^\x00-\x7F\xA0-\xFF]/g, '')  // Remove non-ASCII except extended Latin
      .replace(/⦿|⚡|📄|🛡️|🌐|⚙️|📊|📈|⚠️|🔴|🟠|🟡|🟢|🔵/g, '') // Remove common symbols
      .trim()
  }

  const exportPDF = () => {
    const doc = new jsPDF({ unit: 'mm', format: 'a4' })
    const pageWidth = doc.internal.pageSize.getWidth()
    const pageHeight = doc.internal.pageSize.getHeight()
    const margin = 15
    const headerHeight = 54
    const items = tab === 'cyber' ? filteredFeeds : filteredGlobeEvents

    const now = new Date()
    const generatedDate = now.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
    const reportTime = now.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }) + ' UTC'

    const severityColor = (severity: string): [number, number, number] => {
      const normalized = severity?.toUpperCase()
      return normalized === 'CRITICAL' ? [220, 38, 38]
        : normalized === 'HIGH' ? [234, 88, 12]
        : normalized === 'MEDIUM' ? [202, 138, 4]
        : normalized === 'LOW' ? [22, 163, 74]
        : normalized === 'INFO' ? [37, 99, 235]
        : [107, 119, 145]
    }

    const countBySeverity = (severity: string) => {
      if (tab === 'cyber') {
        return (filteredFeeds as CyberThreatFeed[]).filter(f => f.risk_level.toUpperCase() === severity.toUpperCase()).length
      }
      return (filteredGlobeEvents as GlobeEvent[]).filter(e => e.severity.toUpperCase() === severity.toUpperCase()).length
    }

    const stats: Array<{ label: string; count: number; color: [number, number, number]; bg: [number, number, number] }> = [
      { label: 'CRITICAL', count: countBySeverity('Critical'), color: [220, 38, 38], bg: [248, 224, 224] },
      { label: 'HIGH', count: countBySeverity('High'), color: [234, 88, 12], bg: [255, 237, 213] },
      { label: 'MEDIUM', count: countBySeverity('Medium'), color: [202, 138, 4], bg: [254, 243, 199] },
      { label: 'LOW', count: countBySeverity('Low'), color: [22, 163, 74], bg: [220, 252, 231] },
    ]

    doc.setFillColor(10, 15, 30)
    doc.rect(0, 0, pageWidth, headerHeight, 'F')

    doc.setFont('helvetica', 'bold')
    doc.setFontSize(20)
    doc.setTextColor(255, 255, 255)
    doc.text('JULIUS INTELLIGENCE REPORT', margin, 22)

    doc.setDrawColor(0, 212, 255)
    doc.setLineWidth(1.2)
    doc.line(margin, 24, margin + 72, 24)

    doc.setFontSize(9)
    doc.setFont('helvetica', 'normal')
    doc.setTextColor(0, 212, 255)
    doc.text('GLOBAL THREAT INTELLIGENCE', margin, 30)

    const badgeText = 'UNCLASSIFIED'
    doc.setFont('helvetica', 'bold')
    doc.setFontSize(8)
    const badgeWidth = doc.getTextWidth(badgeText) + 10
    const badgeHeight = 9
    const badgeX = pageWidth - margin - badgeWidth
    const badgeY = 14
    doc.setFillColor(0, 212, 255)
    doc.roundedRect(badgeX, badgeY, badgeWidth, badgeHeight, 2, 2, 'F')
    doc.setTextColor(255, 255, 255)
    doc.text(badgeText, badgeX + badgeWidth / 2, badgeY + 6, { align: 'center' })

    const infoTop = headerHeight - 2
    doc.setFillColor(244, 246, 249)
    doc.roundedRect(margin, infoTop, pageWidth - margin * 2, 18, 3, 3, 'F')
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(8)
    doc.setTextColor(92, 102, 122)
    doc.text(`Generated: ${generatedDate}`, margin + 3, infoTop + 6)
    doc.text(`Report Time: ${reportTime}`, margin + 3, infoTop + 13)
    doc.text(`Total Entries: ${items.length}`, pageWidth - margin - 3, infoTop + 10, { align: 'right' })

    const statsTop = infoTop + 26
    const boxWidth = (pageWidth - margin * 2 - 9) / 4
    const boxHeight = 24

    stats.forEach((stat, index) => {
      const x = margin + index * (boxWidth + 3)
      doc.setFillColor(...stat.bg)
      doc.roundedRect(x, statsTop, boxWidth, boxHeight, 3, 3, 'F')
      doc.setFont('helvetica', 'bold')
      doc.setFontSize(16)
      doc.setTextColor(...stat.color)
      doc.text(`${stat.count}`, x + boxWidth / 2, statsTop + 11, { align: 'center' })
      doc.setFont('helvetica', 'normal')
      doc.setFontSize(8)
      doc.text(stat.label, x + boxWidth / 2, statsTop + 18, { align: 'center' })
    })

    const tableStartY = statsTop + boxHeight + 10
    const summaryHeaders = tab === 'cyber'
      ? ['IP Address', 'Country', 'Source', 'Risk Level']
      : ['Event', 'Country', 'Category', 'Severity']

    const tableData = tab === 'cyber'
      ? (items as CyberThreatFeed[]).slice(0, 100).map((f: CyberThreatFeed) => [
        stripEmoji(f.ip || '—'),
        stripEmoji(countryName(f.country || '')) || '—',
        stripEmoji(f.source || '—'),
        stripEmoji(f.risk_level || 'UNKNOWN').toUpperCase()
      ])
      : (items as GlobeEvent[]).slice(0, 100).map((e: GlobeEvent) => [
        stripEmoji(e.title || '—'),
        stripEmoji(e.country || '—') || '—',
        stripEmoji(CATEGORY_CONFIG[e.category]?.label || e.category),
        stripEmoji(e.severity || 'UNKNOWN').toUpperCase()
      ])

    autoTable(doc, {
      head: [summaryHeaders],
      body: tableData,
      startY: tableStartY,
      margin: { left: margin, right: margin, top: 0, bottom: margin },
      tableLineColor: [224, 229, 238],
      tableLineWidth: 0.15,
      showHead: 'everyPage',
      styles: {
        font: 'helvetica',
        fontSize: 8.5,
        textColor: [35, 43, 60],
        fillColor: [255, 255, 255],
        cellPadding: 4,
        minCellHeight: 10,
      },
      headStyles: {
        fillColor: [26, 32, 53],
        textColor: [255, 255, 255],
        fontStyle: 'bold',
        fontSize: 9,
        halign: 'left',
      },
      alternateRowStyles: {
        fillColor: [248, 249, 250],
      },
      columnStyles: {
        0: { cellWidth: 82 },
        1: { cellWidth: 18, halign: 'center' },
        2: { cellWidth: 45 },
        3: { cellWidth: 35, halign: 'center' },
      },
      didParseCell: (data) => {
        if (data.section === 'body' && data.column.index === 3) {
          data.cell.styles.textColor = [255, 255, 255]
          data.cell.styles.fontStyle = 'bold'
          data.cell.styles.fillColor = [255, 255, 255]
        }
      },
      willDrawCell: (data) => {
        if (data.section === 'body') {
          const severity = data.cell.text[0]?.toString().toUpperCase() || ''
          const color = severityColor(severity)

          if (data.column.index === 0) {
            doc.setFillColor(...color)
            doc.rect(data.cell.x - 2.5, data.cell.y + 1, 2, data.cell.height - 2, 'F')
          }

          if (data.column.index === 3) {
            const badgeText = severity || 'UNKNOWN'
            const badgeWidth = doc.getTextWidth(badgeText) + 8
            const badgeHeight = data.cell.height - 6
            const badgeX = data.cell.x + (data.cell.width - badgeWidth) / 2
            const badgeY = data.cell.y + 3
            doc.setFillColor(...color)
            doc.roundedRect(badgeX, badgeY, badgeWidth, badgeHeight, 2, 2, 'F')
            doc.setTextColor(255, 255, 255)
          }
        }
      },
      didDrawPage: (data) => {
        const footerY = pageHeight - 12
        doc.setDrawColor(0, 212, 255)
        doc.setLineWidth(0.7)
        doc.line(margin, footerY - 2, pageWidth - margin, footerY - 2)
        doc.setFillColor(10, 15, 30)
        doc.rect(0, footerY - 1, pageWidth, 13, 'F')
        doc.setFont('helvetica', 'normal')
        doc.setFontSize(8)
        doc.setTextColor(255, 255, 255)
        doc.text('JULIUS INTELLIGENCE PLATFORM', margin, footerY + 6)
        doc.text(`Page ${data.pageNumber}`, pageWidth - margin, footerY + 6, { align: 'right' })
      }
    })

    const filename = `julius-intelligence-report-${new Date().toISOString().split('T')[0]}.pdf`
    doc.save(filename)
  }

  const criticalCount = filteredFeeds.filter((f: CyberThreatFeed) => f.risk_level === 'Critical').length
  const highCount = filteredFeeds.filter((f: CyberThreatFeed) => f.risk_level === 'High').length

  return (
    <div className="p-6 h-full flex flex-col">
      {/* ── Header ──────────────────────────────────────────────── */}
      <div className="flex justify-between items-start mb-4">
        <div>
          <h1 className="text-2xl font-bold text-julius-text tracking-wide flex items-center gap-3">
            🌐 Global Threat Intelligence
          </h1>
          <p className="text-sm text-julius-muted mt-1">
            Real-time worldwide threats & intelligence events
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={exportPDF}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600/20 border border-blue-500/30 rounded-lg text-blue-400 text-xs font-bold tracking-wider hover:bg-blue-600/30 transition-colors"
          >
            📄 EXPORT PDF
          </button>
          <div className="text-xs text-julius-muted flex flex-col items-end gap-1">
            {isLoading ? (
              <span className="flex items-center gap-1 text-julius-accent">
                <span className="animate-spin text-base">⟳</span> Fetching...
              </span>
            ) : (
              <span className="flex items-center gap-1 text-green-400">● Live — {lastUpdated}</span>
            )}
          </div>
        </div>
      </div>

      {/* ── Tab switcher ─────────────────────────────────────────── */}
      <div className="flex gap-1 mb-4 bg-julius-surface rounded-lg p-1 self-start border border-julius-border">
        <button
          onClick={() => setTab('intelligence')}
          className={`px-4 py-2 rounded-md text-xs font-bold tracking-wider transition-colors
            ${tab === 'intelligence' ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30' : 'text-julius-muted hover:text-julius-text'}`}
        >
          🛰️ Intelligence Events ({globeEvents.length})
        </button>
        <button
          onClick={() => setTab('cyber')}
          className={`px-4 py-2 rounded-md text-xs font-bold tracking-wider transition-colors
            ${tab === 'cyber' ? 'bg-red-600/20 text-red-400 border border-red-500/30' : 'text-julius-muted hover:text-julius-text'}`}
        >
          ⚡ Cyber Threats ({feeds.length})
        </button>
      </div>

      {/* ── Stats row ────────────────────────────────────────────── */}
      <div className="grid grid-cols-4 gap-3 mb-4">
        {tab === 'intelligence' ? (
          <>
            <StatCard label="Total Events" value={filteredGlobeEvents.length} color="#3b82f6" />
            <StatCard label="Conflicts" value={globeEvents.filter(e => e.category === 'conflict' || e.category === 'hotspot').length} color="#ef4444" />
            <StatCard label="Natural" value={globeEvents.filter(e => e.category === 'natural').length} color="#f97316" />
            <StatCard label="Cyber" value={globeEvents.filter(e => e.category === 'cyber').length} color="#a855f7" />
          </>
        ) : (
          <>
            <StatCard label="Total Threats" value={filteredFeeds.length} color="#3b82f6" />
            <StatCard label="Critical" value={criticalCount} color="#ef4444" />
            <StatCard label="High" value={highCount} color="#f97316" />
            <StatCard label="Sources" value={Object.keys(sourceSummary).length} color="#22c55e" />
          </>
        )}
      </div>

      {error ? (
        <div className="bg-red-500/10 border border-red-500/50 p-4 text-red-500 text-sm rounded">
          Failed to fetch live threat feeds.
        </div>
      ) : (
        <>
          {/* ── Filters ─────────────────────────────────────────── */}
          <div className="flex flex-col sm:flex-row gap-3 mb-4">
            <input
              type="text"
              placeholder={tab === 'cyber' ? 'Search IP, tag, country...' : 'Search event, country, description...'}
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="bg-julius-surface2 border border-julius-border px-3 py-1.5 focus:border-julius-accent outline-none text-sm text-julius-text flex-1 rounded"
            />
            {tab === 'cyber' && (
              <div className="flex gap-2 shrink-0 flex-wrap">
                <select value={filterRegion} onChange={e => { setFilterRegion(e.target.value); setFilterCountry('All Countries') }}
                  className="bg-julius-surface2 border border-julius-border px-3 py-1.5 focus:border-julius-accent outline-none text-sm text-julius-text rounded">
                  {ALL_REGIONS.map(r => <option key={r} value={r}>{r === 'All Regions' ? '🌐 All Regions' : `📍 ${r}`}</option>)}
                </select>
                <select value={filterCountry} onChange={e => setFilterCountry(e.target.value)}
                  className="bg-julius-surface2 border border-julius-border px-3 py-1.5 focus:border-julius-accent outline-none text-sm text-julius-text rounded">
                  {availableCountries.map(c => <option key={c} value={c}>{c === 'All Countries' ? '🏳️ All Countries' : `🏳️ ${countryName(c)}`}</option>)}
                </select>
                <select value={filterRisk} onChange={e => setFilterRisk(e.target.value)}
                  className="bg-julius-surface2 border border-julius-border px-3 py-1.5 focus:border-julius-accent outline-none text-sm text-julius-text rounded">
                  {risks.map(r => <option key={r} value={r}>Risk: {r}</option>)}
                </select>
                <select value={filterSource} onChange={e => setFilterSource(e.target.value)}
                  className="bg-julius-surface2 border border-julius-border px-3 py-1.5 focus:border-julius-accent outline-none text-sm text-julius-text rounded">
                  {(sources as string[]).map(s => <option key={s} value={s}>Source: {s}</option>)}
                </select>
              </div>
            )}
          </div>

          {/* ── Table ───────────────────────────────────────────── */}
          <div className="bg-julius-surface border border-julius-border flex-1 overflow-auto rounded-lg">
            {tab === 'intelligence' ? (
              <IntelligenceTable events={filteredGlobeEvents} />
            ) : (
              <CyberTable feeds={filteredFeeds} isLoading={isLoading} totalFeeds={feeds.length} />
            )}
          </div>
        </>
      )}
    </div>
  )
}

// ─── Stat Card ────────────────────────────────────────────────────────────────
function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="rounded-lg p-3 border" style={{ background: color + '08', borderColor: color + '25' }}>
      <div className="text-[10px] font-bold tracking-widest uppercase" style={{ color: color + 'cc' }}>{label}</div>
      <div className="text-xl font-bold mt-1" style={{ color }}>{value}</div>
    </div>
  )
}

// ─── Intelligence Events Table ────────────────────────────────────────────────
function IntelligenceTable({ events }: { events: GlobeEvent[] }) {
  return (
    <table className="w-full text-left text-sm">
      <thead className="bg-julius-surface2 sticky top-0 z-10 shadow">
        <tr>
          <th className="px-4 py-3 font-semibold text-julius-text border-b border-julius-border">Category</th>
          <th className="px-4 py-3 font-semibold text-julius-text border-b border-julius-border">Event</th>
          <th className="px-4 py-3 font-semibold text-julius-text border-b border-julius-border">Country</th>
          <th className="px-4 py-3 font-semibold text-julius-text border-b border-julius-border">Severity</th>
          <th className="px-4 py-3 font-semibold text-julius-text border-b border-julius-border">Description</th>
          <th className="px-4 py-3 font-semibold text-julius-text border-b border-julius-border">Source</th>
          <th className="px-4 py-3 font-semibold text-julius-text border-b border-julius-border">Coords</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-julius-border text-julius-muted">
        {events.map(e => {
          const cfg = CATEGORY_CONFIG[e.category]
          const sevColor = e.severity === 'critical' ? '#ef4444' : e.severity === 'high' ? '#f97316' : e.severity === 'medium' ? '#eab308' : '#22c55e'
          return (
            <tr key={e.id} className="hover:bg-julius-surface2/50 transition-colors">
              <td className="px-4 py-2.5">
                <span className="inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded"
                  style={{ background: cfg.color + '12', color: cfg.color, border: `1px solid ${cfg.color}30` }}>
                  {cfg.emoji} {cfg.label}
                </span>
              </td>
              <td className="px-4 py-2.5 text-julius-text font-medium text-xs">{e.title}</td>
              <td className="px-4 py-2.5 text-xs text-blue-300">{e.country || '—'}</td>
              <td className="px-4 py-2.5">
                <span className="px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase"
                  style={{ background: sevColor + '15', color: sevColor, border: `1px solid ${sevColor}30` }}>
                  {e.severity}
                </span>
              </td>
              <td className="px-4 py-2.5 text-xs max-w-[220px] truncate" title={e.description}>{e.description}</td>
              <td className="px-4 py-2.5 text-xs text-julius-muted">{e.source || '—'}</td>
              <td className="px-4 py-2.5 text-xs font-mono text-blue-400/60">{e.lat.toFixed(2)}, {e.lng.toFixed(2)}</td>
            </tr>
          )
        })}
        {events.length === 0 && (
          <tr><td colSpan={7} className="px-4 py-8 text-center text-julius-muted">No intelligence events match the search.</td></tr>
        )}
      </tbody>
    </table>
  )
}

// ─── Cyber Threats Table ──────────────────────────────────────────────────────
function CyberTable({ feeds, isLoading, totalFeeds }: { feeds: CyberThreatFeed[]; isLoading: boolean; totalFeeds: number }) {
  return (
    <table className="w-full text-left text-sm">
      <thead className="bg-julius-surface2 sticky top-0 z-10 shadow">
        <tr>
          <th className="px-4 py-3 font-semibold text-julius-text border-b border-julius-border">IP Address</th>
          <th className="px-4 py-3 font-semibold text-julius-text border-b border-julius-border">Country</th>
          <th className="px-4 py-3 font-semibold text-julius-text border-b border-julius-border">Region</th>
          <th className="px-4 py-3 font-semibold text-julius-text border-b border-julius-border">Source</th>
          <th className="px-4 py-3 font-semibold text-julius-text border-b border-julius-border">Risk</th>
          <th className="px-4 py-3 font-semibold text-julius-text border-b border-julius-border">Tags</th>
          <th className="px-4 py-3 font-semibold text-julius-text border-b border-julius-border">Details</th>
          <th className="px-4 py-3 font-semibold text-julius-text border-b border-julius-border">Last Seen</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-julius-border text-julius-muted">
        {feeds.map((feed: CyberThreatFeed) => {
          const cc = (feed.country || '').toUpperCase()
          const region = COUNTRY_TO_REGION[cc] || '—'
          return (
            <tr key={feed.id} className="hover:bg-julius-surface2/50 transition-colors">
              <td className="px-4 py-2.5 font-mono text-julius-text">{feed.ip}</td>
              <td className="px-4 py-2.5 text-xs">
                {feed.country ? <span className="text-blue-300">{countryName(feed.country)}</span> : <span className="opacity-30">—</span>}
              </td>
              <td className="px-4 py-2.5 text-xs text-julius-muted">{region}</td>
              <td className="px-4 py-2.5 text-xs text-julius-muted">{feed.source}</td>
              <td className="px-4 py-2.5">
                <span className={`px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase
                  ${feed.risk_level === 'Critical' ? 'bg-red-500/10 text-red-500 border border-red-500/30'
                  : feed.risk_level === 'High' ? 'bg-orange-500/10 text-orange-500 border border-orange-500/30'
                  : feed.risk_level === 'Medium' ? 'bg-yellow-500/10 text-yellow-500 border border-yellow-500/30'
                  : 'bg-green-500/10 text-green-500 border border-green-500/30'}`}>
                  {feed.risk_level}
                </span>
              </td>
              <td className="px-4 py-2.5">
                <div className="flex flex-wrap gap-1">
                  {feed.tags.map((tag: string) => (
                    <span key={tag} className="text-[10px] bg-julius-accent/10 text-julius-accent px-1.5 py-0.5 rounded border border-julius-accent/20">{tag}</span>
                  ))}
                </div>
              </td>
              <td className="px-4 py-2.5 text-xs max-w-[200px] truncate" title={feed.details}>{feed.details || '—'}</td>
              <td className="px-4 py-2.5 text-xs opacity-70">{feed.last_seen ? new Date(feed.last_seen).toLocaleString() : '—'}</td>
            </tr>
          )
        })}
        {feeds.length === 0 && !isLoading && (
          <tr>
            <td colSpan={8} className="px-4 py-8 text-center text-julius-muted">
              {totalFeeds === 0 ? 'Loading live threat data...' : 'No threats match the selected filters.'}
            </td>
          </tr>
        )}
      </tbody>
    </table>
  )
}
