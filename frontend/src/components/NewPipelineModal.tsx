import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { checkConflicts, fetchAgents, fetchGitHubIssue, fetchPipelineTemplates } from '@/api/client'
import { useCreatePipeline } from '@/hooks/useCreatePipeline'
import DirectoryPicker from '@/components/DirectoryPicker'
import type { CustomStepInput, Pipeline } from '@/types/api'

interface Props {
  open: boolean
  onClose: () => void
}

type Mode = 'template' | 'custom'

/** Internal step entry with a stable React key. */
interface StepEntry extends CustomStepInput {
  _id: string
}

const inputCls =
  'w-full rounded border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none'

const btnSecondary =
  'rounded border border-gray-600 bg-gray-800 px-3 py-1 text-xs text-gray-300 hover:bg-gray-700 hover:text-white disabled:opacity-40'

// ---------------------------------------------------------------------------
// Custom step builder state helpers
// ---------------------------------------------------------------------------

function moveStep(steps: StepEntry[], from: number, to: number): StepEntry[] {
  if (to < 0 || to >= steps.length) return steps
  const next = [...steps]
  const [item] = next.splice(from, 1)
  next.splice(to, 0, item)
  return next
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function NewPipelineModal({ open, onClose }: Props) {
  // ---- Shared fields ----
  const [title, setTitle] = useState('')
  const [prompt, setPrompt] = useState('')
  const [branch, setBranch] = useState('')
  const [workingDir, setWorkingDir] = useState('')

  // ---- Mode ----
  const [mode, setMode] = useState<Mode>('template')

  // ---- Template mode ----
  const [template, setTemplate] = useState('')

  // ---- Custom mode ----
  const [customSteps, setCustomSteps] = useState<StepEntry[]>([])
  const [pendingAgent, setPendingAgent] = useState<string>('')
  const [customStepsError, setCustomStepsError] = useState<string | null>(null)

  // ---- GitHub Issue panel ----
  const [ghRepo, setGhRepo] = useState('')
  const [ghNumber, setGhNumber] = useState('')
  const [ghFetching, setGhFetching] = useState(false)
  const [ghPreview, setGhPreview] = useState<string | null>(null)
  const [ghError, setGhError] = useState<string | null>(null)

  // ---- Directory picker ----
  const [showDirPicker, setShowDirPicker] = useState(false)

  // ---- Conflict detection ----
  const [conflicts, setConflicts] = useState<Pipeline[]>([])
  const [conflictsAcknowledged, setConflictsAcknowledged] = useState(false)
  const [conflictsError, setConflictsError] = useState(false)

  const createPipeline = useCreatePipeline()
  const firstInputRef = useRef<HTMLInputElement>(null)

  // ---- Data fetching ----
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

  const { data: agents, isLoading: agentsLoading } = useQuery({
    queryKey: ['agents'],
    queryFn: fetchAgents,
    staleTime: Infinity,
  })

  // ---- Reset ----
  const reset = createPipeline.reset
  useEffect(() => {
    if (open) {
      setTitle('')
      setTemplate('')
      setPrompt('')
      setBranch('')
      setWorkingDir('')
      setMode('template')
      setCustomSteps([])
      setPendingAgent('')
      setCustomStepsError(null)
      setGhRepo('')
      setGhNumber('')
      setGhFetching(false)
      setGhPreview(null)
      setGhError(null)
      setConflicts([])
      setConflictsAcknowledged(false)
      setConflictsError(false)
      reset()
    }
  }, [open, reset])

  // Focus first input after the modal is fully painted.
  useLayoutEffect(() => {
    if (open) {
      firstInputRef.current?.focus()
    }
  }, [open])

  // ---- Keyboard ----
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

  // Fetch conflicts when workingDir settles (debounced 400 ms). Reset acknowledgement
  // whenever the directory changes so a fresh warning is always shown.
  useEffect(() => {
    setConflictsAcknowledged(false)
    setConflictsError(false)
    if (!workingDir) {
      setConflicts([])
      return
    }
    let cancelled = false
    const timer = setTimeout(() => {
      checkConflicts(workingDir)
        .then((result) => {
          if (!cancelled) {
            setConflicts(result)
            setConflictsError(false)
          }
        })
        .catch(() => {
          if (!cancelled) {
            setConflicts([])
            setConflictsError(true)
          }
        })
    }, 400)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [workingDir])

  if (!open) return null

  // ---- Custom step actions ----
  const addAgentStep = () => {
    if (!pendingAgent) return
    setCustomSteps((prev) => [...prev, { _id: crypto.randomUUID(), type: 'agent', agent: pendingAgent }])
    setPendingAgent('')
    setCustomStepsError(null)
  }

  const addApprovalStep = () => {
    setCustomSteps((prev) => [...prev, { _id: crypto.randomUUID(), type: 'approval' }])
    setCustomStepsError(null)
  }

  const removeStep = (idx: number) => {
    setCustomSteps((prev) => prev.filter((_, i) => i !== idx))
  }

  const updateStepModel = (idx: number, model: string) => {
    setCustomSteps((prev) => prev.map((s, i) => (i === idx ? { ...s, model: model || undefined } : s)))
  }

  // ---- GitHub issue fetch ----
  const handleFetchIssue = async () => {
    const num = parseInt(ghNumber, 10)
    if (!ghRepo || isNaN(num)) {
      setGhError('Enter a valid repo (owner/repo) and issue number.')
      return
    }
    setGhFetching(true)
    setGhError(null)
    setGhPreview(null)
    try {
      const issue = await fetchGitHubIssue(ghRepo, num)
      setGhPreview(`#${issue.number}: ${issue.title}`)
    } catch (err) {
      setGhError(err instanceof Error ? err.message : 'Failed to fetch issue.')
    } finally {
      setGhFetching(false)
    }
  }

  // ---- Submit ----
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()

    if (mode === 'template') {
      if (!template) return
    } else {
      const agentSteps = customSteps.filter((s) => s.type === 'agent')
      if (agentSteps.length === 0) {
        setCustomStepsError('Add at least one agent step.')
        return
      }
    }

    // Block submission if conflicts are present and not yet acknowledged via the banner button.
    if (conflicts.length > 0 && !conflictsAcknowledged) {
      return
    }

    const ghNum = parseInt(ghNumber, 10)
    const ghFields =
      ghRepo && !isNaN(ghNum) && ghNum >= 1
        ? { github_issue_repo: ghRepo, github_issue_number: ghNum }
        : {}

    // Strip internal _id field before sending to API
    const apiSteps: CustomStepInput[] = customSteps.map(({ _id: _ignored, ...rest }) => rest)

    const req =
      mode === 'template'
        ? {
            template,
            title,
            prompt,
            branch: branch || undefined,
            working_dir: workingDir || undefined,
            ...ghFields,
          }
        : {
            custom_steps: apiSteps,
            title,
            prompt,
            branch: branch || undefined,
            working_dir: workingDir || undefined,
            ...ghFields,
          }

    createPipeline.mutate(req, { onSuccess: () => onClose() })
  }

  const submitDisabled =
    createPipeline.isPending ||
    (mode === 'template' && templatesLoading) ||
    (conflicts.length > 0 && !conflictsAcknowledged)

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
      role="dialog"
      aria-modal="true"
      aria-labelledby="np-heading"
    >
      <div className="w-full max-w-lg rounded-lg border border-gray-700 bg-gray-900 p-6 shadow-xl overflow-y-auto max-h-[90vh]">
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

          {/* Mode toggle */}
          <div>
            <span className="mb-1 block text-sm text-gray-300">Pipeline source</span>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setMode('template')}
                className={`rounded px-3 py-1 text-sm ${
                  mode === 'template'
                    ? 'bg-blue-600 text-white'
                    : 'border border-gray-600 bg-gray-800 text-gray-300 hover:bg-gray-700'
                }`}
              >
                Template
              </button>
              <button
                type="button"
                onClick={() => setMode('custom')}
                className={`rounded px-3 py-1 text-sm ${
                  mode === 'custom'
                    ? 'bg-blue-600 text-white'
                    : 'border border-gray-600 bg-gray-800 text-gray-300 hover:bg-gray-700'
                }`}
              >
                Custom
              </button>
            </div>
          </div>

          {/* Template picker */}
          {mode === 'template' && (
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
          )}

          {/* Custom step builder */}
          {mode === 'custom' && (
            <div className="space-y-2">
              <span className="block text-sm text-gray-300">Steps</span>

              {/* Step list */}
              {customSteps.length === 0 && (
                <p className="text-xs text-gray-500">No steps yet. Add an agent step or approval gate below.</p>
              )}
              {customSteps.map((step, idx) => (
                <div
                  key={step._id}
                  className="flex items-center gap-2 rounded border border-gray-700 bg-gray-800 px-3 py-2"
                >
                  <span className="flex-1 text-sm text-white">
                    {step.type === 'agent' ? (
                      <>
                        <span className="text-blue-400">{step.agent}</span>
                        {' — agent'}
                      </>
                    ) : (
                      <span className="text-yellow-400">Approval Gate</span>
                    )}
                  </span>
                  {step.type === 'agent' && (
                    <input
                      type="text"
                      value={step.model ?? ''}
                      onChange={(e) => updateStepModel(idx, e.target.value)}
                      placeholder="model (optional)"
                      className="w-36 rounded border border-gray-700 bg-gray-900 px-2 py-1 text-xs text-white placeholder-gray-600 focus:border-blue-500 focus:outline-none"
                    />
                  )}
                  <button
                    type="button"
                    onClick={() => setCustomSteps((s) => moveStep(s, idx, idx - 1))}
                    disabled={idx === 0}
                    className={btnSecondary}
                    title="Move up"
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    onClick={() => setCustomSteps((s) => moveStep(s, idx, idx + 1))}
                    disabled={idx === customSteps.length - 1}
                    className={btnSecondary}
                    title="Move down"
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    onClick={() => removeStep(idx)}
                    className="rounded px-2 py-1 text-xs text-red-400 hover:bg-gray-700"
                    title="Remove"
                  >
                    ✕
                  </button>
                </div>
              ))}

              {/* Add step controls */}
              <div className="flex gap-2 pt-1">
                <select
                  value={pendingAgent}
                  onChange={(e) => setPendingAgent(e.target.value)}
                  className="flex-1 rounded border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-white focus:border-blue-500 focus:outline-none"
                >
                  <option value="">{agentsLoading ? 'Loading agents…' : 'Pick agent…'}</option>
                  {agents?.map((a) => (
                    <option key={a.name} value={a.name}>
                      {a.name} — {a.description}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={addAgentStep}
                  disabled={!pendingAgent}
                  className="rounded bg-blue-700 px-3 py-1 text-xs text-white hover:bg-blue-600 disabled:opacity-40"
                >
                  + Agent Step
                </button>
                <button
                  type="button"
                  onClick={addApprovalStep}
                  className="rounded bg-yellow-700 px-3 py-1 text-xs text-white hover:bg-yellow-600"
                >
                  + Approval Gate
                </button>
              </div>

              {customStepsError && <p className="text-xs text-red-400">{customStepsError}</p>}
            </div>
          )}

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

          {/* GitHub Issue (optional) */}
          <details className="group">
            <summary className="cursor-pointer text-sm text-gray-400 hover:text-gray-200 select-none">
              GitHub Issue <span className="text-gray-500">(optional — enriches prompt)</span>
            </summary>
            <div className="mt-2 space-y-2 pl-1">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={ghRepo}
                  onChange={(e) => {
                    setGhRepo(e.target.value)
                    setGhPreview(null)
                    setGhError(null)
                  }}
                  placeholder="owner/repo"
                  className="flex-1 rounded border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                />
                <input
                  type="number"
                  value={ghNumber}
                  onChange={(e) => {
                    setGhNumber(e.target.value)
                    setGhPreview(null)
                    setGhError(null)
                  }}
                  placeholder="#"
                  className="w-20 rounded border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => void handleFetchIssue()}
                  disabled={ghFetching || !ghRepo || isNaN(parseInt(ghNumber, 10)) || parseInt(ghNumber, 10) < 1}
                  className="rounded bg-gray-700 px-3 py-1 text-xs text-white hover:bg-gray-600 disabled:opacity-40"
                >
                  {ghFetching ? 'Fetching…' : 'Fetch'}
                </button>
              </div>
              {ghPreview && (
                <p className="text-xs text-green-400">
                  Found: {ghPreview}
                </p>
              )}
              {ghError && <p className="text-xs text-red-400">{ghError}</p>}
            </div>
          </details>

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
            <div className="flex gap-2">
              <input
                id="np-working-dir"
                type="text"
                value={workingDir}
                onChange={(e) => setWorkingDir(e.target.value)}
                className={`${inputCls} flex-1`}
                placeholder="/path/to/project"
              />
              <button
                type="button"
                onClick={() => setShowDirPicker(true)}
                className="rounded border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white flex-shrink-0"
                title="Browse…"
              >
                Browse…
              </button>
            </div>
          </div>

          {/* Conflict check error */}
          {conflictsError && (
            <p className="text-xs text-orange-400">
              Could not check for conflicts — proceed with caution.
            </p>
          )}

          {/* Conflict warning */}
          {conflicts.length > 0 && (
            <div role="alert" className="rounded border border-orange-500 bg-orange-900 px-3 py-2 text-sm text-orange-100">
              <p className="font-semibold mb-1">Conflict detected in this working directory:</p>
              <ul className="list-disc list-inside space-y-0.5 text-xs text-orange-200 mb-2">
                {conflicts.map((p) => (
                  <li key={p.id}>
                    <span className="font-medium">{p.title}</span>
                    {' '}(#{p.id}, {p.status})
                  </li>
                ))}
              </ul>
              {conflictsAcknowledged ? (
                <p className="text-xs text-orange-300">
                  Acknowledged. Click <strong>Create</strong> to proceed.
                </p>
              ) : (
                <div className="flex items-center gap-3">
                  <p className="flex-1 text-xs text-orange-300">
                    Starting may cause merge conflicts.
                  </p>
                  <button
                    type="button"
                    onClick={() => setConflictsAcknowledged(true)}
                    className="rounded border border-orange-400 px-2 py-1 text-xs text-orange-200 hover:bg-orange-800 whitespace-nowrap"
                  >
                    Proceed anyway
                  </button>
                </div>
              )}
            </div>
          )}

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

      {showDirPicker && (
        <DirectoryPicker
          onSelect={(path) => {
            setWorkingDir(path)
            setShowDirPicker(false)
          }}
          onClose={() => setShowDirPicker(false)}
        />
      )}
    </div>
  )
}
