import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchPipelineTemplates } from '@/api/client'
import { useCreatePipeline } from '@/hooks/useCreatePipeline'

interface Props {
  open: boolean
  onClose: () => void
}

const inputCls =
  'w-full rounded border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none'

export default function NewPipelineModal({ open, onClose }: Props) {
  const [title, setTitle] = useState('')
  const [template, setTemplate] = useState('')
  const [prompt, setPrompt] = useState('')
  const [branch, setBranch] = useState('')
  const [workingDir, setWorkingDir] = useState('')

  const createPipeline = useCreatePipeline()
  const firstInputRef = useRef<HTMLInputElement>(null)

  const {
    data: templates,
    isLoading: templatesLoading,
    isError: templatesError,
    refetch: refetchTemplates,
  } = useQuery({
    queryKey: ['pipeline-templates'],
    queryFn: fetchPipelineTemplates,
    staleTime: Infinity,
  })

  // Reset form and mutation state when modal opens; move focus to first field
  const reset = createPipeline.reset
  useEffect(() => {
    if (open) {
      setTitle('')
      setTemplate('')
      setPrompt('')
      setBranch('')
      setWorkingDir('')
      reset()
      // Defer focus until the DOM is visible
      setTimeout(() => firstInputRef.current?.focus(), 0)
    }
  }, [open, reset])

  // Close on Escape
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    },
    [onClose],
  )
  useEffect(() => {
    if (!open) return
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open, handleKeyDown])

  if (!open) return null

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    createPipeline.mutate(
      { title, template, prompt, branch: branch || undefined, working_dir: workingDir || undefined },
      { onSuccess: () => onClose() },
    )
  }

  const submitDisabled = createPipeline.isPending || templatesLoading

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
      role="dialog"
      aria-modal="true"
      aria-labelledby="np-heading"
    >
      <div className="w-full max-w-lg rounded-lg border border-gray-700 bg-gray-900 p-6 shadow-xl">
        <h2 id="np-heading" className="mb-5 text-lg font-semibold text-white">
          New Pipeline
        </h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Title */}
          <div>
            <label className="mb-1 block text-sm text-gray-300" htmlFor="np-title">
              Title
            </label>
            <input
              ref={firstInputRef}
              id="np-title"
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className={inputCls}
              placeholder="e.g. Fix login bug"
            />
          </div>

          {/* Template */}
          <div>
            <label className="mb-1 block text-sm text-gray-300" htmlFor="np-template">
              Template
            </label>
            <select
              id="np-template"
              required
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
              className={inputCls}
            >
              <option value="" disabled>
                {templatesLoading
                  ? 'Loading templates…'
                  : templatesError
                    ? 'Failed to load templates'
                    : 'Select a template'}
              </option>
              {templates?.map((t) => (
                <option key={t.name} value={t.name}>
                  {t.name} — {t.description}
                </option>
              ))}
            </select>
            {templatesError && (
              <button
                type="button"
                onClick={() => void refetchTemplates()}
                className="mt-1 text-xs text-blue-400 hover:underline"
              >
                Retry loading templates
              </button>
            )}
          </div>

          {/* Prompt */}
          <div>
            <label className="mb-1 block text-sm text-gray-300" htmlFor="np-prompt">
              Prompt
            </label>
            <textarea
              id="np-prompt"
              required
              rows={4}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              className={inputCls}
              placeholder="Describe what the pipeline should do…"
            />
          </div>

          {/* Branch (optional) */}
          <div>
            <label className="mb-1 block text-sm text-gray-300" htmlFor="np-branch">
              Branch <span className="text-gray-500">(optional)</span>
            </label>
            <input
              id="np-branch"
              type="text"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
              className={inputCls}
              placeholder="e.g. feature/my-fix"
            />
          </div>

          {/* Working Directory (optional) */}
          <div>
            <label className="mb-1 block text-sm text-gray-300" htmlFor="np-working-dir">
              Working Directory <span className="text-gray-500">(optional)</span>
            </label>
            <input
              id="np-working-dir"
              type="text"
              value={workingDir}
              onChange={(e) => setWorkingDir(e.target.value)}
              className={inputCls}
              placeholder="/path/to/project"
            />
          </div>

          {/* Error */}
          {createPipeline.isError && (
            <p className="text-sm text-red-400">{createPipeline.error.message}</p>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded px-4 py-2 text-sm text-gray-300 hover:text-white"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitDisabled}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500 disabled:opacity-50"
            >
              {createPipeline.isPending ? 'Creating…' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
