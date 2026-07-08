import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { reports } from '../lib/api'

type ReportResponse = {
  report_id: string
  generated_at?: string
  summary?: {
    vulnerability_count?: number
    event_count?: number
    threat_entries?: number
  }
}

async function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export function ReportControls() {
  const [report, setReport] = useState<ReportResponse | null>(null)

  const generateMut = useMutation({
    mutationFn: reports.generateFull,
    onSuccess: (data) => setReport(data as ReportResponse),
  })

  const docxMut = useMutation({
    mutationFn: async (reportId: string) => {
      const blob = await reports.downloadDocx(reportId)
      await saveBlob(blob, `${reportId}.docx`)
    },
  })

  const pdfMut = useMutation({
    mutationFn: async (reportId: string) => {
      const blob = await reports.downloadPdf(reportId)
      await saveBlob(blob, `${reportId}.pdf`)
    },
  })

  return (
    <div className="flex items-center gap-2 pointer-events-auto">
      <button
        onClick={() => generateMut.mutate()}
        disabled={generateMut.isPending}
        className="h-7 px-3 rounded border border-julius-accent/40 bg-julius-accent/10 text-[10px] font-black tracking-[0.2em] text-julius-accent hover:bg-julius-accent/20 disabled:opacity-50"
      >
        {generateMut.isPending ? 'Building Report' : 'Generate Full Report'}
      </button>

      {report ? (
        <>
          <button
            onClick={() => docxMut.mutate(report.report_id)}
            disabled={docxMut.isPending}
            className="h-7 px-2 rounded border border-julius-border bg-julius-surface2 text-[10px] font-black tracking-[0.18em] text-julius-text hover:border-julius-accent"
          >
            {docxMut.isPending ? 'DOCX...' : 'Download DOCX'}
          </button>
          <button
            onClick={() => pdfMut.mutate(report.report_id)}
            disabled={pdfMut.isPending}
            className="h-7 px-2 rounded border border-julius-border bg-julius-surface2 text-[10px] font-black tracking-[0.18em] text-julius-text hover:border-julius-accent"
          >
            {pdfMut.isPending ? 'PDF...' : 'Download PDF'}
          </button>
        </>
      ) : null}
    </div>
  )
}
