import { useEffect, useState } from 'react'
import { AlertCircle, CheckCircle2, Key, Loader2, RefreshCw, Save, XCircle, Zap } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { useMemoryHealth } from '../hooks/useMemoryHealth'
import {
  useApplyEmbedding,
  useEmbeddingSettings,
  useStartReindex,
  useTestEmbedding,
} from '../hooks/useEmbeddingSettings'

const PROVIDERS = [
  { id: 'tei', label: 'Bundled TEI (local container)' },
  { id: 'ollama', label: 'Ollama (local)' },
  { id: 'ollama_cloud', label: 'Ollama Cloud' },
]

const providerLabel = (id) => PROVIDERS.find((p) => p.id === id)?.label || id

/**
 * Which model turns documents into vectors. One choice for the whole system, because vectors from different
 * models cannot be compared; changing it needs a re-index. Anyone can see it, only an admin can change it.
 */
export const EmbeddingSettingsCard = () => {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const { data: settings, isLoading } = useEmbeddingSettings()
  const { data: health } = useMemoryHealth()
  const test = useTestEmbedding()
  const apply = useApplyEmbedding()
  const reindex = useStartReindex()

  const [form, setForm] = useState({ provider: 'tei', model: '', baseUrl: '', apiKey: '', clearKey: false })

  // Start the form from what is saved. The key box always starts empty: a saved key is never sent back.
  useEffect(() => {
    if (settings) {
      setForm({
        provider: settings.provider,
        model: settings.model_editable ? settings.model : '',
        baseUrl: '',
        apiKey: '',
        clearKey: false,
      })
    }
  }, [settings])

  if (isLoading || !settings) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-400">
        <Loader2 className="w-4 h-4 animate-spin" />
        Loading embedding settings...
      </div>
    )
  }

  const running = health?.reindex?.state === 'running'
  const total = settings.documents_total ?? health?.documents_total
  const inIndex = settings.documents_in_index ?? health?.documents_in_index
  const missing = total != null && inIndex != null ? Math.max(total - inIndex, 0) : 0
  const progress = health?.reindex
  const sendsOffMachine = form.provider === 'ollama_cloud'

  const set = (patch) => {
    test.reset()
    setForm((current) => ({ ...current, ...patch }))
  }

  const candidate = {
    provider: form.provider,
    model: form.provider === 'tei' ? undefined : form.model.trim(),
    baseUrl: form.provider === 'ollama' ? form.baseUrl.trim() : undefined,
    apiKey: form.provider === 'ollama_cloud' ? form.apiKey : undefined,
    clearKey: form.clearKey,
  }

  const showKeyHint = form.provider === 'ollama_cloud' && settings.provider === 'ollama_cloud' && settings.key_hint

  return (
    <div className="p-4 rounded-lg bg-white/5 space-y-4">
      <div>
        <p className="font-medium">Embedding model</p>
        <p className="text-sm text-gray-400">
          The model that turns your documents into vectors for search. It applies to everyone, and changing it
          means re-indexing your documents.
        </p>
      </div>

      <div className="text-sm space-y-1">
        <p>
          <span className="text-gray-400">Active: </span>
          {providerLabel(settings.provider)} · {settings.model}
          {settings.dim ? ` · vector size ${settings.dim}` : ' · size not measured yet'}
        </p>
        {total != null && inIndex != null && (
          <p className="text-gray-400">
            {inIndex} of {total} documents are in this model&apos;s index
            {settings.source === 'environment' ? ' · set by the environment, not yet saved in Settings' : ''}
          </p>
        )}
      </div>

      {missing > 0 && !running && (
        <div className="p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20 text-yellow-400 text-sm flex items-start gap-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <p>
            {missing} document{missing === 1 ? ' is' : 's are'} not in the current index yet, so search falls back to
            keywords for {missing === 1 ? 'it' : 'them'}. {isAdmin ? 'Re-index to fix this.' : 'Ask an admin to re-index.'}
          </p>
        </div>
      )}

      {progress && progress.state !== 'idle' && (
        <div className="text-sm">
          {progress.state === 'running' && (
            <div>
              <p className="text-gray-300 mb-1">
                Re-indexing: {progress.done + progress.failed} of {progress.total}
                {progress.failed > 0 ? ` (${progress.failed} failed)` : ''}
              </p>
              <div className="h-2 rounded bg-white/10 overflow-hidden">
                <div
                  className="h-full bg-blue-500 transition-all"
                  style={{ width: `${progress.total ? ((progress.done + progress.failed) / progress.total) * 100 : 0}%` }}
                />
              </div>
            </div>
          )}
          {progress.state === 'done' && (
            <p className="text-green-400 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4" />
              Last re-index finished: {progress.done} indexed{progress.failed > 0 ? `, ${progress.failed} failed` : ''}.
            </p>
          )}
          {(progress.state === 'failed' || progress.state === 'stalled') && (
            <p className="text-red-400 flex items-start gap-2">
              <XCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
              {progress.state === 'stalled' ? 'The last re-index stopped reporting. You can start it again.' : 'The last re-index stopped.'}
              {progress.error ? ` ${progress.error}` : ''}
            </p>
          )}
        </div>
      )}

      {!isAdmin && <p className="text-xs text-gray-500">Only an admin can change the embedding model.</p>}

      {isAdmin && (
        <div className="space-y-3 pt-2 border-t border-white/10">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Provider</label>
            <select
              value={form.provider}
              onChange={(e) => set({ provider: e.target.value, apiKey: '', clearKey: false })}
              className="glass-input w-full"
            >
              {PROVIDERS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>

          {form.provider === 'tei' ? (
            <p className="text-xs text-gray-500">TEI serves one model, set by the server (EMBEDDING_MODEL).</p>
          ) : (
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Model</label>
              <input
                type="text"
                value={form.model}
                onChange={(e) => set({ model: e.target.value })}
                className="glass-input w-full"
                placeholder="embeddinggemma"
                autoComplete="off"
              />
            </div>
          )}

          {form.provider === 'ollama' && (
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Ollama URL (optional)</label>
              <input
                type="text"
                value={form.baseUrl}
                onChange={(e) => set({ baseUrl: e.target.value })}
                className="glass-input w-full"
                placeholder={settings.base_url || 'The server default'}
                autoComplete="off"
              />
            </div>
          )}

          {form.provider === 'ollama_cloud' && (
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                {showKeyHint ? 'Replace key' : 'API key'}
              </label>
              <div className="relative">
                <Key className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
                <input
                  type="password"
                  value={form.apiKey}
                  onChange={(e) => set({ apiKey: e.target.value })}
                  className="glass-input w-full pl-10"
                  placeholder={showKeyHint ? `Saved: ••••${settings.key_hint}` : 'Your Ollama API key'}
                  autoComplete="new-password"
                />
              </div>
              <p className="mt-1 text-xs text-gray-500">
                Stored encrypted on the server and never shown again. This is a separate copy from your own Ollama
                Cloud key, because indexing runs for every user.
              </p>
            </div>
          )}

          {sendsOffMachine && (
            <div className="p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20 text-yellow-400 text-xs flex items-start gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <p>
                Document text is sent to ollama.com to be embedded. Ollama&apos;s cloud FAQ describes its data
                handling; read it before using this for sensitive documents. The other two choices keep text on your
                own machine.
              </p>
            </div>
          )}

          {test.data && (
            <p className={`text-sm flex items-start gap-2 ${test.data.ok ? 'text-green-400' : 'text-red-400'}`}>
              {test.data.ok ? <CheckCircle2 className="w-4 h-4 mt-0.5" /> : <XCircle className="w-4 h-4 mt-0.5" />}
              <span>
                {test.data.detail}
                {test.data.ok && test.data.latency_ms != null ? ` (${test.data.latency_ms} ms)` : ''}
              </span>
            </p>
          )}
          {test.isError && (
            <p className="text-sm text-red-400">{test.error?.response?.data?.detail || 'The test could not run.'}</p>
          )}

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => test.mutate(candidate)}
              disabled={test.isPending || apply.isPending}
              className="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 flex items-center gap-2 disabled:opacity-50"
            >
              {test.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
              Test
            </button>
            <button
              type="button"
              onClick={() => apply.mutate(candidate)}
              disabled={apply.isPending || test.isPending}
              className="glass-button-primary px-4 py-2 flex items-center gap-2 disabled:opacity-50"
            >
              {apply.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              Save
            </button>
            <button
              type="button"
              onClick={() => reindex.mutate()}
              disabled={reindex.isPending || running}
              className="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 flex items-center gap-2 disabled:opacity-50 ml-auto"
            >
              {running || reindex.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
              Re-index documents
            </button>
          </div>
          <p className="text-xs text-gray-500">
            Save only works if the model really returns vectors. Re-indexing re-embeds every stored document with the
            active model; search keeps working with keywords meanwhile.
          </p>
        </div>
      )}
    </div>
  )
}
