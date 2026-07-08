import { useState } from 'react'
import { CyberOpsTerminal } from './CyberOpsTerminal'

export function ChatOverlay() {
  const [open, setOpen] = useState(false)

  return (
    <>
      {/* FAB */}
      {!open && (
        <button onClick={() => setOpen(true)}
          className="fixed bottom-6 right-6 z-50 w-12 h-12 rounded-full bg-julius-accent hover:bg-julius-accent/90 text-white flex items-center justify-center shadow-xl transition-transform hover:scale-105">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
        </button>
      )}

      {/* Cyber Ops Terminal Overlay */}
      {open && <CyberOpsTerminal onClose={() => setOpen(false)} />}
    </>
  )
}
