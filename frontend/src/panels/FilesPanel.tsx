import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { files } from '../lib/api'

interface FileEntry {
  name: string
  path: string
  is_directory: boolean
  extension?: string
  size_bytes?: number
  file_type?: string
  is_binary?: boolean
}

export function FilesPanel() {
  const [path, setPath] = useState('.')
  const [navStack, setNavStack] = useState<string[]>([])
  const [viewing, setViewing] = useState<string | null>(null)
  const [fileContent, setFileContent] = useState('')
  const [fileMeta, setFileMeta] = useState<{ is_binary?: boolean; file_type?: string; size_human?: string; download_url?: string; message?: string } | null>(null)
  const [editing, setEditing] = useState(false)
  const [editContent, setEditContent] = useState('')
  const [showNewFile, setShowNewFile] = useState(false)
  const [showNewDir, setShowNewDir] = useState(false)
  const [newName, setNewName] = useState('')
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)

  const { data: listing, isLoading, refetch } = useQuery({
    queryKey: ['files-list', path],
    queryFn: () => files.list(path)
  })

  const { data: sandboxInfo } = useQuery({
    queryKey: ['sandbox-info'],
    queryFn: files.sandboxInfo
  })

  const entries = (listing as { data?: { entries?: FileEntry[] } } | undefined)?.data?.entries ?? []
  const sandbox = sandboxInfo as { total_files?: number; total_size_bytes?: number; security?: { sandboxed?: boolean } } | undefined

  const readMut = useMutation({
    mutationFn: (filePath: string) => files.read(filePath),
    onSuccess: (data, filePath) => {
      const d = data as { data?: { content?: string; is_binary?: boolean; file_type?: string; size_human?: string; download_url?: string; message?: string } }
      setViewing(filePath)
      setFileMeta(d.data || null)
      setFileContent(d.data?.content || '')
      setEditing(false)
    },
  })

  const saveMut = useMutation({
    mutationFn: () => {
      if (viewing == null) throw new Error('No file selected')
      return files.operate('write', viewing, editContent)
    },
    onSuccess: () => { setEditing(false); setFileContent(editContent); refetch() },
  })

  const createFileMut = useMutation({
    mutationFn: () => files.operate('write', path === '.' ? newName : `${path}/${newName}`, ''),
    onSuccess: () => { setShowNewFile(false); setNewName(''); refetch() },
  })

  const createDirMut = useMutation({
    mutationFn: () => files.operate('mkdir', path === '.' ? newName : `${path}/${newName}`),
    onSuccess: () => { setShowNewDir(false); setNewName(''); refetch() },
  })

  const deleteMut = useMutation({
    mutationFn: (p: string) => files.operate('delete', p, undefined, true),
    onSuccess: () => {
      setConfirmDelete(null)
      if (viewing === confirmDelete) { setViewing(null); setFileMeta(null) }
      refetch()
    },
    onError: () => {
      // Try direct delete endpoint as fallback
      if (confirmDelete) {
        fetch(`/api/files/delete?path=${encodeURIComponent(confirmDelete)}`, { method: 'DELETE' })
          .then(() => { setConfirmDelete(null); refetch() })
          .catch(console.error)
      }
    }
  })

  const navigateTo = (entryPath: string, isDir: boolean) => {
    if (!isDir) { readMut.mutate(entryPath); return }
    setNavStack(s => [...s, path])
    setPath(entryPath)
    setViewing(null)
    setFileMeta(null)
  }

  const navigateUp = () => {
    const prev = navStack[navStack.length - 1] ?? '.'
    setNavStack(s => s.slice(0, -1))
    setPath(prev)
    setViewing(null)
    setFileMeta(null)
  }

  const handleDownload = (filePath: string) => {
    window.open(`/api/files/download?path=${encodeURIComponent(filePath)}`, '_blank')
  }

  const fmt = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1048576).toFixed(2)} MB`
  }

  return (
    <div className="p-6 space-y-6 overflow-y-auto h-full">
      <h1 className="text-xl font-bold tracking-wide">File Browser</h1>

      {sandbox && (
        <div className="bg-julius-surface border border-julius-border rounded-xl p-4">
          <div className="flex gap-6 flex-wrap">
            <Chip label="Files" value={String(sandbox.total_files ?? 0)} />
            <Chip label="Size" value={fmt(Number(sandbox.total_size_bytes ?? 0))} />
            <Chip label="Sandbox" value={sandbox.security?.sandboxed ? 'Active' : 'Off'}
              color={sandbox.security?.sandboxed ? 'text-julius-green' : 'text-julius-red'} />
          </div>
        </div>
      )}

      {/* Toolbar */}
      <div className="flex items-center gap-3">
        {navStack.length > 0 && (
          <button onClick={navigateUp}
            className="text-julius-accent hover:text-julius-text text-sm px-2 py-1 border border-julius-border rounded">
            ← Back
          </button>
        )}
        <div className="flex-1 bg-julius-surface border border-julius-border rounded-lg px-4 py-2 text-xs font-mono">
          <span className="text-julius-muted">sandbox:/</span>
          <span className="text-julius-text">{path === '.' ? '' : path}</span>
        </div>
        <button onClick={() => { setShowNewFile(true); setNewName('') }}
          className="text-xs text-julius-accent hover:text-julius-text px-2 py-1 border border-julius-border rounded">
          + File
        </button>
        <button onClick={() => { setShowNewDir(true); setNewName('') }}
          className="text-xs text-julius-accent hover:text-julius-text px-2 py-1 border border-julius-border rounded">
          + Folder
        </button>
        <button onClick={() => refetch()}
          className="text-julius-accent hover:text-julius-text text-sm px-2 py-1 border border-julius-border rounded">
          Refresh
        </button>
      </div>

      {/* New file/dir forms */}
      {(showNewFile || showNewDir) && (
        <div className="bg-julius-surface border border-julius-border rounded-xl p-4 flex items-center gap-3">
          <span className="text-xs text-julius-muted">{showNewFile ? 'New File:' : 'New Folder:'}</span>
          <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="name" autoFocus
            className="flex-1 bg-julius-bg border border-julius-border rounded px-2 py-1.5 text-xs text-julius-text focus:outline-none" />
          <button onClick={() => showNewFile ? createFileMut.mutate() : createDirMut.mutate()} disabled={!newName}
            className="text-xs bg-julius-accent text-white px-3 py-1.5 rounded disabled:opacity-40">
            Create
          </button>
          <button onClick={() => { setShowNewFile(false); setShowNewDir(false) }}
            className="text-xs text-julius-muted hover:text-julius-text">
            Cancel
          </button>
        </div>
      )}

      {/* Split view */}
      <div className="flex gap-6">
        {/* File listing */}
        <div className={`bg-julius-surface border border-julius-border rounded-xl p-4 ${viewing ? 'w-1/2' : 'w-full'}`}>
          {isLoading ? (
            <div className="text-xs text-julius-muted text-center py-8">Loading...</div>
          ) : entries.length === 0 ? (
            <div className="text-xs text-julius-muted text-center py-8">Empty directory</div>
          ) : (
            <div className="space-y-1">
              {entries.map((e: FileEntry, i: number) => (
                <div key={i}
                  className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-julius-surface2 transition-colors cursor-pointer group"
                  onClick={() => navigateTo(e.path, e.is_directory)}>
                  <span className="text-base">{e.is_directory ? '📁' : fileIcon(e.extension ?? null, e.is_binary)}</span>
                  <span className={`text-xs flex-1 ${e.is_directory ? 'text-julius-accent font-semibold' : 'text-julius-text'}`}>
                    {e.name}
                  </span>
                  {e.is_binary && !e.is_directory && (
                    <span className="text-[9px] text-julius-muted bg-julius-surface2 px-1.5 py-0.5 rounded">
                      {e.file_type || 'Binary'}
                    </span>
                  )}
                  <span className="text-[10px] text-julius-muted font-mono">
                    {e.is_directory ? '-' : fmt(e.size_bytes ?? 0)}
                  </span>
                  {/* Download button for binary files */}
                  {e.is_binary && !e.is_directory && (
                    <button
                      onClick={ev => { ev.stopPropagation(); handleDownload(e.path) }}
                      className="opacity-0 group-hover:opacity-100 text-julius-accent hover:text-julius-text text-xs px-1.5 py-0.5 border border-julius-border rounded">
                      ⬇
                    </button>
                  )}
                  <button
                    onClick={ev => { ev.stopPropagation(); setConfirmDelete(e.path ?? null) }}
                    className="opacity-0 group-hover:opacity-100 text-julius-muted hover:text-julius-red text-xs">
                    🗑️
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* File viewer */}
        {viewing && (
          <div className="w-1/2 bg-julius-surface border border-julius-border rounded-xl p-4 flex flex-col">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold truncate">{viewing.split('/').pop()}</h3>
              <div className="flex gap-2">
                {/* Download button always visible */}
                <button
                  onClick={() => handleDownload(viewing)}
                  className="text-[10px] bg-julius-accent text-white px-2 py-1 rounded hover:opacity-90">
                  ⬇ Download
                </button>
                {/* Edit button only for text files */}
                {!fileMeta?.is_binary && !editing && (
                  <button onClick={() => { setEditContent(fileContent); setEditing(true) }}
                    className="text-[10px] text-julius-accent hover:text-julius-text px-2 py-1 border border-julius-border rounded">
                    Edit
                  </button>
                )}
                {editing && (
                  <>
                    <button onClick={() => saveMut.mutate()} disabled={saveMut.isPending}
                      className="text-[10px] bg-julius-accent text-white px-2 py-1 rounded disabled:opacity-40">
                      Save
                    </button>
                    <button onClick={() => setEditing(false)}
                      className="text-[10px] text-julius-muted hover:text-julius-text px-2 py-1 border border-julius-border rounded">
                      Cancel
                    </button>
                  </>
                )}
                <button onClick={() => { setViewing(null); setFileMeta(null) }}
                  className="text-julius-muted hover:text-julius-text text-sm">
                  ✕
                </button>
              </div>
            </div>

            {readMut.isPending ? (
              <div className="text-xs text-julius-muted text-center py-8">Loading...</div>
            ) : fileMeta?.is_binary ? (
              /* Binary file preview */
              <div className="flex-1 bg-julius-bg border border-julius-border rounded p-6 flex flex-col items-center justify-center gap-4">
                <span className="text-4xl">{fileIcon(viewing.split('.').pop() ? '.' + viewing.split('.').pop() : null, true)}</span>
                <div className="text-center">
                  <p className="text-sm font-semibold text-julius-text">{fileMeta.file_type}</p>
                  <p className="text-xs text-julius-muted mt-1">{fileMeta.size_human}</p>
                  <p className="text-xs text-julius-muted mt-2">{fileMeta.message}</p>
                </div>
                <button
                  onClick={() => handleDownload(viewing)}
                  className="mt-2 bg-julius-accent text-white text-sm px-6 py-2 rounded-lg hover:opacity-90 transition-opacity">
                  ⬇ Download File
                </button>
              </div>
            ) : editing ? (
              <textarea value={editContent} onChange={e => setEditContent(e.target.value)}
                className="flex-1 bg-julius-bg border border-julius-border rounded p-3 text-xs font-mono text-julius-text focus:outline-none resize-none" />
            ) : (
              <pre className="flex-1 bg-julius-bg border border-julius-border rounded p-3 text-xs font-mono text-julius-text overflow-auto whitespace-pre-wrap">
                {fileContent || '(empty file)'}
              </pre>
            )}
          </div>
        )}
      </div>

      {/* Delete confirmation */}
      {confirmDelete && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center"
          onClick={() => setConfirmDelete(null)}>
          <div className="bg-julius-surface border border-julius-border rounded-xl p-6 max-w-sm"
            onClick={e => e.stopPropagation()}>
            <h3 className="text-sm font-bold mb-2">Confirm Delete</h3>
            <p className="text-xs text-julius-muted mb-4">
              Delete <span className="font-mono text-julius-text">{confirmDelete}</span>?
            </p>
            <div className="flex gap-2">
              <button onClick={() => setConfirmDelete(null)}
                className="flex-1 text-xs py-2 rounded border border-julius-border hover:bg-julius-surface2">
                Cancel
              </button>
              <button
                onClick={() => deleteMut.mutate(confirmDelete)}
                disabled={deleteMut.isPending}
                className="flex-1 text-xs py-2 rounded bg-julius-red text-white hover:bg-julius-red/90 disabled:opacity-40">
                {deleteMut.isPending ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function Chip({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex flex-col items-center gap-0.5">
      <span className="text-[9px] text-julius-muted uppercase tracking-wider">{label}</span>
      <span className={`text-xs font-mono ${color || 'text-julius-text'}`}>{value}</span>
    </div>
  )
}

function fileIcon(ext: string | null, _isBinary?: boolean): string {
  if (!ext) return '📄'
  const e = ext.toLowerCase()
  if (e === '.pdf') return '📕'
  if (['.docx', '.doc'].includes(e)) return '📘'
  if (['.xlsx', '.xls', '.csv'].includes(e)) return '📗'
  if (['.pptx', '.ppt'].includes(e)) return '📙'
  if (['.py', '.js', '.ts', '.tsx'].includes(e)) return '🐍'
  if (['.json', '.yaml', '.toml'].includes(e)) return '⚙️'
  if (['.md', '.txt', '.log'].includes(e)) return '📝'
  if (['.zip', '.tar', '.gz'].includes(e)) return '🗜️'
  if (['.png', '.jpg', '.jpeg', '.gif'].includes(e)) return '🖼️'
  return '📄'
}
