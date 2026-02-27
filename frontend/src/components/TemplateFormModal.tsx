import { useEffect, useState } from 'react'
import type { AgentStepWrite, ApprovalStepWrite, PipelineStepWrite, PipelineTemplateResponse, PipelineWriteRequest } from '@/types/api'
import { useAgents } from '@/hooks/useAgents'

interface Props {
  template?: PipelineTemplateResponse
  onClose: () => void
  onSubmit: (req: PipelineWriteRequest) => void
  isPending: boolean
  error: string | null
}

const inputClass =
  'w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-gray-100 text-xs focus:outline-none focus:border-blue-500'

function templateToWriteRequest(t: PipelineTemplateResponse): PipelineWriteRequest {
  return {
    name: t.name,
    description: t.description,
    steps: t.steps.map((s) =>
      s.type === 'agent'
        ? ({ type: 'agent', agent: s.agent ?? '', description: s.description, model: null } satisfies AgentStepWrite)
        : ({ type: 'approval', description: s.description } satisfies ApprovalStepWrite),
    ),
  }
}

function makeKeys(count: number): string[] {
  return Array.from({ length: count }, () => crypto.randomUUID())
}

const EMPTY: PipelineWriteRequest = { name: '', description: '', steps: [] }

export default function TemplateFormModal({ template, onClose, onSubmit, isPending, error }: Props) {
  const isEdit = template !== undefined
  const { data: agents } = useAgents()
  const initial = template ? templateToWriteRequest(template) : EMPTY
  const [form, setForm] = useState<PipelineWriteRequest>(initial)
  // Stable identity keys for step list items — avoids incorrect reconciliation on reorder/remove
  const [stepKeys, setStepKeys] = useState<string[]>(() => makeKeys(initial.steps.length))

  useEffect(() => {
    const next = template ? templateToWriteRequest(template) : EMPTY
    setForm(next)
    setStepKeys(makeKeys(next.steps.length))
  }, [template])

  function setField<K extends 'name' | 'description'>(key: K, value: string) {
    setForm((f) => ({ ...f, [key]: value }))
  }

  function updateStep(index: number, patch: Partial<PipelineStepWrite>) {
    setForm((f) => ({
      ...f,
      steps: f.steps.map((s, i) => (i === index ? ({ ...s, ...patch } as PipelineStepWrite) : s)),
    }))
  }

  function addAgentStep() {
    const firstAgent = agents?.[0]?.name ?? ''
    setForm((f) => ({
      ...f,
      steps: [...f.steps, { type: 'agent', agent: firstAgent, description: '', model: null } satisfies AgentStepWrite],
    }))
    setStepKeys((keys) => [...keys, crypto.randomUUID()])
  }

  function addApprovalStep() {
    setForm((f) => ({
      ...f,
      steps: [...f.steps, { type: 'approval', description: '' } satisfies ApprovalStepWrite],
    }))
    setStepKeys((keys) => [...keys, crypto.randomUUID()])
  }

  function removeStep(index: number) {
    setForm((f) => ({ ...f, steps: f.steps.filter((_, i) => i !== index) }))
    setStepKeys((keys) => keys.filter((_, i) => i !== index))
  }

  function moveStep(index: number, direction: -1 | 1) {
    setForm((f) => {
      const steps = [...f.steps]
      const target = index + direction
      if (target < 0 || target >= steps.length) return f
      ;[steps[index], steps[target]] = [steps[target], steps[index]]
      return { ...f, steps }
    })
    setStepKeys((keys) => {
      const next = [...keys]
      const target = index + direction
      if (target < 0 || target >= next.length) return next
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    onSubmit(form)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-gray-900 border border-gray-700 rounded-lg w-full max-w-2xl p-6 max-h-[90vh] overflow-y-auto">
        <h2 className="text-white font-semibold text-sm mb-4">{isEdit ? 'Edit Template' : 'New Template'}</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-gray-400 text-xs mb-1">Name</label>
            <input
              className={inputClass}
              value={form.name}
              onChange={(e) => setField('name', e.target.value)}
              disabled={isEdit}
              required
            />
          </div>
          <div>
            <label className="block text-gray-400 text-xs mb-1">Description</label>
            <input
              className={inputClass}
              value={form.description}
              onChange={(e) => setField('description', e.target.value)}
              required
            />
          </div>

          <div>
            <label className="block text-gray-400 text-xs mb-2">Steps</label>
            <div className="space-y-2">
              {form.steps.map((step, i) => (
                <div key={stepKeys[i]} className="flex items-start gap-2 p-2 bg-gray-800 rounded border border-gray-700">
                  <div className="flex flex-col gap-0.5 mt-0.5">
                    <button
                      type="button"
                      className="text-gray-500 hover:text-gray-300 text-xs leading-none"
                      onClick={() => moveStep(i, -1)}
                      disabled={i === 0}
                    >
                      ▲
                    </button>
                    <button
                      type="button"
                      className="text-gray-500 hover:text-gray-300 text-xs leading-none"
                      onClick={() => moveStep(i, 1)}
                      disabled={i === form.steps.length - 1}
                    >
                      ▼
                    </button>
                  </div>
                  <div className="flex-1 space-y-1.5">
                    <span
                      className={`inline-block px-1.5 py-0.5 rounded text-xs ${
                        step.type === 'agent' ? 'bg-blue-900 text-blue-200' : 'bg-yellow-900 text-yellow-200'
                      }`}
                    >
                      {step.type}
                    </span>
                    {step.type === 'agent' && (
                      <div className="flex gap-2">
                        <div className="flex-1">
                          <label className="block text-gray-500 text-xs mb-0.5">Agent</label>
                          <select
                            className={inputClass}
                            value={step.agent}
                            onChange={(e) => updateStep(i, { agent: e.target.value })}
                          >
                            {agents?.map((a) => (
                              <option key={a.name} value={a.name}>
                                {a.name}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div className="flex-1">
                          <label className="block text-gray-500 text-xs mb-0.5">Model (optional)</label>
                          <input
                            className={inputClass}
                            value={step.model ?? ''}
                            onChange={(e) => updateStep(i, { model: e.target.value || null })}
                          />
                        </div>
                      </div>
                    )}
                    <div>
                      <label className="block text-gray-500 text-xs mb-0.5">Description</label>
                      <input
                        className={inputClass}
                        value={step.description}
                        onChange={(e) => updateStep(i, { description: e.target.value })}
                      />
                    </div>
                  </div>
                  <button
                    type="button"
                    className="text-gray-600 hover:text-red-400 text-xs mt-0.5"
                    onClick={() => removeStep(i)}
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
            <div className="flex gap-2 mt-2">
              <button
                type="button"
                className="px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 text-gray-200 text-xs"
                onClick={addAgentStep}
              >
                + Agent step
              </button>
              <button
                type="button"
                className="px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 text-gray-200 text-xs"
                onClick={addApprovalStep}
              >
                + Approval step
              </button>
            </div>
          </div>

          {error && <p className="text-red-400 text-xs">{error}</p>}
          <div className="flex gap-2 justify-end pt-2">
            <button
              type="button"
              className="px-3 py-1.5 rounded bg-gray-700 hover:bg-gray-600 text-gray-200 text-xs"
              onClick={onClose}
              disabled={isPending}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-3 py-1.5 rounded bg-blue-700 hover:bg-blue-600 text-white text-xs disabled:opacity-50"
              disabled={isPending}
            >
              {isPending ? 'Saving…' : isEdit ? 'Save Changes' : 'Create Template'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
