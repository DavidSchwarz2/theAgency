import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchBrowse } from '@/api/client'
import type { FsEntry } from '@/types/api'

interface Props {
  onSelect: (path: string) => void
  onClose: () => void
}

export default function DirectoryPicker({ onSelect, onClose }: Props) {
  const [currentPath, setCurrentPath] = useState<string | undefined>(undefined)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['fs-browse', currentPath ?? ''],
    queryFn: () => fetchBrowse(currentPath, true),
  })

  const breadcrumbs = buildBreadcrumbs(data?.path ?? '')

  const handleEntry = (entry: FsEntry) => {
    if (entry.is_dir) setCurrentPath(entry.path)
  }

  const handleBreadcrumb = (path: string) => {
    setCurrentPath(path)
  }

  const handleUp = () => {
    if (data?.parent) setCurrentPath(data.parent)
  }

  return (
    <div className="fixed inset-0 z-60 flex items-center justify-center bg-black/80" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-lg border border-gray-600 bg-gray-900 shadow-2xl flex flex-col"
        style={{ maxHeight: '70vh' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-700 px-4 py-3">
          <span className="text-sm font-semibold text-white">Select Working Directory</span>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-lg leading-none">✕</button>
        </div>

        {/* Breadcrumb */}
        <div className="flex items-center gap-1 px-4 py-2 border-b border-gray-800 overflow-x-auto text-xs text-gray-400 flex-shrink-0">
          {data?.parent != null && (
            <button onClick={handleUp} className="mr-1 text-gray-500 hover:text-white flex-shrink-0" title="Up">
              ↑
            </button>
          )}
          {breadcrumbs.map((crumb, i) => (
            <span key={crumb.path} className="flex items-center gap-1 flex-shrink-0">
              {i > 0 && <span className="text-gray-600">/</span>}
              <button
                onClick={() => handleBreadcrumb(crumb.path)}
                className={`hover:text-white truncate max-w-[120px] ${i === breadcrumbs.length - 1 ? 'text-white font-medium' : 'hover:underline'}`}
                title={crumb.path}
              >
                {crumb.label}
              </button>
            </span>
          ))}
        </div>

        {/* Entry list */}
        <div className="flex-1 overflow-y-auto min-h-0">
          {isLoading && (
            <div className="px-4 py-6 text-center text-sm text-gray-500">Loading…</div>
          )}
          {isError && (
            <div className="px-4 py-6 text-center text-sm text-red-400">Failed to load directory.</div>
          )}
          {!isLoading && !isError && data?.entries.length === 0 && (
            <div className="px-4 py-6 text-center text-sm text-gray-500">No subdirectories.</div>
          )}
          {data?.entries.map((entry) => (
            <button
              key={entry.path}
              onClick={() => handleEntry(entry)}
              className="w-full flex items-center gap-3 px-4 py-2 text-sm text-left hover:bg-gray-800 text-gray-200"
            >
              <span className="text-yellow-400 flex-shrink-0">📁</span>
              <span className="truncate">{entry.name}</span>
            </button>
          ))}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-gray-700 px-4 py-3 flex-shrink-0">
          <span className="text-xs text-gray-400 truncate max-w-[260px]" title={data?.path ?? ''}>
            {data?.path ?? '…'}
          </span>
          <div className="flex gap-2 flex-shrink-0 ml-2">
            <button
              onClick={onClose}
              className="rounded border border-gray-600 bg-gray-800 px-3 py-1 text-xs text-gray-300 hover:bg-gray-700"
            >
              Cancel
            </button>
            <button
              onClick={() => data?.path && onSelect(data.path)}
              disabled={!data?.path}
              className="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-500 disabled:opacity-40"
            >
              Select
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildBreadcrumbs(fullPath: string): { label: string; path: string }[] {
  if (!fullPath) return []
  const parts = fullPath.split('/').filter(Boolean)
  return [
    { label: '/', path: '/' },
    ...parts.map((part, i) => ({
      label: part,
      path: '/' + parts.slice(0, i + 1).join('/'),
    })),
  ]
}
