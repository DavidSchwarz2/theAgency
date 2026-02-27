import { useState } from 'react'
import TemplateFormModal from '@/components/TemplateFormModal'
import { useTemplateMutations, useTemplates } from '@/hooks/useTemplates'
import type { PipelineTemplateResponse, PipelineWriteRequest } from '@/types/api'

export default function TemplatesPage() {
  const { data: templates, isLoading, error } = useTemplates()
  const { create, update, remove } = useTemplateMutations()
  const [modalTemplate, setModalTemplate] = useState<PipelineTemplateResponse | null | 'new'>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)

  function handleSubmit(req: PipelineWriteRequest) {
    if (modalTemplate === 'new') {
      create.mutate(req, { onSuccess: () => setModalTemplate(null) })
    } else if (modalTemplate) {
      update.mutate({ name: modalTemplate.name, req }, { onSuccess: () => setModalTemplate(null) })
    }
  }

  const mutationError =
    (create.error instanceof Error ? create.error.message : null) ??
    (update.error instanceof Error ? update.error.message : null)

  const isPending = create.isPending || update.isPending

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-white font-semibold text-lg">Pipeline Templates</h1>
        <button
          className="px-3 py-1.5 rounded bg-blue-700 hover:bg-blue-600 text-white text-xs"
          onClick={() => setModalTemplate('new')}
        >
          New Template
        </button>
      </div>

      {isLoading && <p className="text-gray-500 text-sm">Loading…</p>}
      {error instanceof Error && <p className="text-red-400 text-sm">{error.message}</p>}

      <div className="space-y-3">
        {templates?.map((template) => (
          <article key={template.name} className="rounded-lg border border-gray-800 bg-gray-900 p-4">
            <div className="flex items-start justify-between gap-3 mb-2">
              <div>
                <h3 className="font-semibold text-white text-sm">{template.name}</h3>
                <p className="text-gray-400 text-xs mt-0.5">{template.description}</p>
              </div>
              <div className="flex gap-2 shrink-0">
                <button
                  className="px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 text-gray-200 text-xs"
                  onClick={() => setModalTemplate(template)}
                >
                  Edit
                </button>
                {deleteConfirm === template.name ? (
                  <span className="flex items-center gap-1">
                    <button
                      className="px-2 py-1 rounded bg-red-700 hover:bg-red-600 text-white text-xs disabled:opacity-50"
                      disabled={remove.isPending}
                      onClick={() => remove.mutate(template.name, { onSuccess: () => setDeleteConfirm(null) })}
                    >
                      Confirm
                    </button>
                    <button
                      className="px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 text-gray-200 text-xs"
                      onClick={() => setDeleteConfirm(null)}
                    >
                      Cancel
                    </button>
                  </span>
                ) : (
                  <button
                    className="px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 text-gray-200 text-xs"
                    onClick={() => setDeleteConfirm(template.name)}
                  >
                    Delete
                  </button>
                )}
              </div>
            </div>
            <ol className="space-y-0.5">
              {template.steps.map((step, i) => (
                <li key={i} className="flex items-center gap-2 text-xs">
                  <span className="text-gray-600">{i + 1}.</span>
                  <span
                    className={`px-1.5 py-0.5 rounded ${
                      step.type === 'agent' ? 'bg-blue-900 text-blue-300' : 'bg-yellow-900 text-yellow-300'
                    }`}
                  >
                    {step.type}
                  </span>
                  {step.type === 'agent' && <span className="text-gray-300">{step.agent}</span>}
                  {step.description && <span className="text-gray-500">— {step.description}</span>}
                </li>
              ))}
            </ol>
            {remove.error instanceof Error && deleteConfirm === template.name && (
              <p className="text-red-400 text-xs mt-1">{remove.error.message}</p>
            )}
          </article>
        ))}
      </div>

      {modalTemplate !== null && (
        <TemplateFormModal
          template={modalTemplate === 'new' ? undefined : modalTemplate}
          onClose={() => setModalTemplate(null)}
          onSubmit={handleSubmit}
          isPending={isPending}
          error={mutationError}
        />
      )}
    </div>
  )
}
