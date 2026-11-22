import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, Loader2, Save } from 'lucide-react'
import { useModelSettings, useSaveModelSettings } from '../hooks/useModelSettings'
import { modelKey } from '../lib/providers'

// Turns the server's state into an editable draft: for each provider, the ids that are switched on.
const toDraft = (settings) => ({
  enabled: Object.fromEntries(
    (settings?.providers || []).map((p) => [p.id, p.models.filter((m) => m.enabled).map((m) => m.id)])
  ),
  defaultModel: settings?.default ? { provider: settings.default.provider, model: settings.default.model } : null,
})

const sameList = (a = [], b = []) => a.length === b.length && a.every((id) => b.includes(id))

/** Which models appear in the chat list, and which one new conversations start on. */
export const ModelSelection = () => {
  const { data: settings, isLoading, isError } = useModelSettings()
  const save = useSaveModelSettings()
  const [draft, setDraft] = useState(null)

  useEffect(() => {
    if (settings) setDraft(toDraft(settings))
  }, [settings])

  const dirty = useMemo(() => {
    if (!settings || !draft) return false
    const saved = toDraft(settings)
    const sameDefault =
      saved.defaultModel?.provider === draft.defaultModel?.provider && saved.defaultModel?.model === draft.defaultModel?.model
    return !sameDefault || settings.providers.some((p) => !sameList(saved.enabled[p.id], draft.enabled[p.id]))
  }, [settings, draft])

  if (isLoading || !draft) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-400">
        <Loader2 className="w-4 h-4 animate-spin" />
        Loading models...
      </div>
    )
  }
  if (isError) {
    return <p className="text-sm text-yellow-400">Could not load your models. Is the backend running?</p>
  }

  const toggle = (providerId, modelId) => {
    setDraft((current) => {
      const on = current.enabled[providerId] || []
      const next = on.includes(modelId) ? on.filter((id) => id !== modelId) : [...on, modelId]
      // Switching a model off also clears it as the default.
      const lostDefault =
        current.defaultModel?.provider === providerId &&
        current.defaultModel?.model === modelId &&
        !next.includes(modelId)
      return {
        enabled: { ...current.enabled, [providerId]: next },
        defaultModel: lostDefault ? null : current.defaultModel,
      }
    })
  }

  const setAll = (provider, value) => {
    setDraft((current) => {
      const next = value ? provider.models.map((m) => m.id) : []
      const lostDefault = !value && current.defaultModel?.provider === provider.id
      return {
        enabled: { ...current.enabled, [provider.id]: next },
        defaultModel: lostDefault ? null : current.defaultModel,
      }
    })
  }

  const handleSave = () => {
    // A provider with every model on is left out, so models it lists later are on by default too.
    const enabledModels = {}
    settings.providers.forEach((p) => {
      const on = draft.enabled[p.id] || []
      if (p.models.some((m) => !on.includes(m.id))) enabledModels[p.id] = on
    })
    save.mutate({
      enabledModels: Object.keys(enabledModels).length > 0 ? enabledModels : null,
      defaultModel: draft.defaultModel,
    })
  }

  const defaultKey = draft.defaultModel ? modelKey(draft.defaultModel.provider, draft.defaultModel.model) : ''

  return (
    <div className="space-y-4">
      {settings.providers.map((provider) => {
        const on = draft.enabled[provider.id] || []
        return (
          <div key={provider.id} className="p-4 rounded-lg bg-white/5">
            <div className="flex items-center justify-between mb-3">
              <div>
                <p className="font-medium">{provider.label}</p>
                <p className="text-xs text-gray-500">
                  {provider.configured
                    ? `${on.length} of ${provider.models.length} models in your chat list`
                    : 'Add a key in the section above to use this provider'}
                </p>
              </div>
              {provider.models.length > 0 && (
                <div className="flex gap-2 text-xs">
                  <button type="button" onClick={() => setAll(provider, true)} className="px-2 py-1 rounded bg-white/10 hover:bg-white/20">
                    All
                  </button>
                  <button type="button" onClick={() => setAll(provider, false)} className="px-2 py-1 rounded bg-white/10 hover:bg-white/20">
                    None
                  </button>
                </div>
              )}
            </div>

            {provider.configured && provider.models.length === 0 && (
              <p className="text-sm text-gray-400">No models were returned. Check the connection above.</p>
            )}

            <div className="space-y-1">
              {provider.models.map((model) => {
                const checked = on.includes(model.id)
                return (
                  <div key={model.id} className="flex items-center justify-between gap-3 px-2 py-1.5 rounded hover:bg-white/5">
                    <label className="flex items-center gap-2 text-sm cursor-pointer min-w-0">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggle(provider.id, model.id)}
                        className="accent-blue-500"
                      />
                      <span className="truncate">{model.name}</span>
                      {!model.available && (
                        <span className="inline-flex items-center gap-1 text-xs text-yellow-400" title="Not listed right now">
                          <AlertCircle className="w-3 h-3" /> not listed
                        </span>
                      )}
                    </label>
                    <label className={`flex items-center gap-1 text-xs ${checked ? 'text-gray-300 cursor-pointer' : 'text-gray-600'}`}>
                      <input
                        type="radio"
                        name="default-model"
                        disabled={!checked}
                        checked={defaultKey === modelKey(provider.id, model.id)}
                        onChange={() => setDraft((c) => ({ ...c, defaultModel: { provider: provider.id, model: model.id } }))}
                        className="accent-blue-500"
                      />
                      Default
                    </label>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}

      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => setDraft((c) => ({ ...c, defaultModel: null }))}
          disabled={!draft.defaultModel}
          className="text-xs text-gray-400 hover:text-gray-200 disabled:opacity-40"
        >
          Clear default
        </button>
        <button
          type="button"
          onClick={handleSave}
          disabled={!dirty || save.isPending}
          className="glass-button-primary px-4 py-2 flex items-center gap-2 disabled:opacity-50"
        >
          {save.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          Save models
        </button>
      </div>
    </div>
  )
}
