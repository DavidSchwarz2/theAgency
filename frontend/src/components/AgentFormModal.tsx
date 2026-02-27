import { useEffect, useState } from 'react'
import type { AgentProfileResponse, AgentWriteRequest } from '@/types/api'

interface Props {
  agent?: AgentProfileResponse
  onClose: () => void
  onSubmit: (req: AgentWriteRequest) => void
  isPending: boolean
  error: string | null
}

const EMPTY: AgentWriteRequest = {
  name: '',
  description: '',
  opencode_agent: '',
  default_model: null,
  system_prompt_additions: '',
}

const inputClass =
  'w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-gray-100 text-xs focus:outline-none focus:border-blue-500'

export default function AgentFormModal({ agent, onClose, onSubmit, isPending, error }: Props) {
  const isEdit = agent !== undefined
  const [form, setForm] = useState<AgentWriteRequest>(EMPTY)

  useEffect(() => {
    setForm(
      agent
        ? {
            name: agent.name,
            description: agent.description,
            opencode_agent: agent.opencode_agent,
            default_model: agent.default_model,
            system_prompt_additions: '',
          }
        : EMPTY,
    )
  }, [agent])

  function set<K extends keyof AgentWriteRequest>(key: K, value: AgentWriteRequest[K]) {
    setForm((f) => ({ ...f, [key]: value }))
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    onSubmit(form)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-gray-900 border border-gray-700 rounded-lg w-full max-w-lg p-6">
        <h2 className="text-white font-semibold text-sm mb-4">{isEdit ? 'Edit Agent' : 'New Agent'}</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <Field label="Name">
            <input
              className={inputClass}
              value={form.name}
              onChange={(e) => set('name', e.target.value)}
              disabled={isEdit}
              required
            />
          </Field>
          <Field label="Description">
            <input
              className={inputClass}
              value={form.description}
              onChange={(e) => set('description', e.target.value)}
              required
            />
          </Field>
          <Field label="OpenCode Agent">
            <input
              className={inputClass}
              value={form.opencode_agent}
              onChange={(e) => set('opencode_agent', e.target.value)}
              required
            />
          </Field>
          <Field label="Default Model (optional)">
            <input
              className={inputClass}
              value={form.default_model ?? ''}
              onChange={(e) => set('default_model', e.target.value || null)}
            />
          </Field>
          <Field label="System Prompt Additions (optional)">
            <textarea
              className={`${inputClass} h-20 resize-y`}
              value={form.system_prompt_additions}
              onChange={(e) => set('system_prompt_additions', e.target.value)}
            />
          </Field>
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
              {isPending ? 'Saving…' : isEdit ? 'Save Changes' : 'Create Agent'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-gray-400 text-xs mb-1">{label}</label>
      {children}
    </div>
  )
}
