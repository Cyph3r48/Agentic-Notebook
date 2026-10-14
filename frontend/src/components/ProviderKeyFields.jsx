import { useState } from 'react'
import { AlertCircle, ExternalLink, Key, Loader2, Save, Trash2, Zap } from 'lucide-react'
import { toast } from 'sonner'
import { settingsAPI } from '../api/settings'

// Keys saved in the browser by older versions of this page. They are moved to the server on request.
const LEGACY_KEYS = {
  anthropic: { apiKey: 'claude_api_key' },
  ollama: { apiKey: 'ollama_api_key', baseUrl: 'ollama_url' },
}

const readLegacy = (provider) => {
  try {
    const names = LEGACY_KEYS[provider] || {}
    return {
      apiKey: (names.apiKey && localStorage.getItem(names.apiKey)) || '',
      baseUrl: (names.baseUrl && localStorage.getItem(names.baseUrl)) || '',
    }
  } catch {
    return { apiKey: '', baseUrl: '' }
  }
}

const clearLegacy = (provider) => {
  try {
    Object.values(LEGACY_KEYS[provider] || {}).forEach((name) => localStorage.removeItem(name))
  } catch {
    // Storage can be unavailable; nothing to clean up then.
  }
}

const errorText = (error, fallback) => {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg
  return fallback
}

/**
 * Key entry for one provider. The input always starts empty: a saved key is never sent back to the
 * browser, only a hint such as "••••a1b2".
 */
export const ProviderKeyFields = ({
  provider,
  status,
  isAdmin = false,
  placeholder,
  helpUrl,
  helpLabel,
  onChanged,
}) => {
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [legacy, setLegacy] = useState(() => readLegacy(provider))

  const showUrl = provider === 'ollama' && isAdmin
  const hasLegacy = Boolean(legacy.apiKey || (showUrl && legacy.baseUrl))
  const hasSavedKey = status?.source === 'user' && Boolean(status?.key_hint)

  const run = async (action, successMessage, failureMessage) => {
    setBusy(true)
    try {
      const result = await action()
      if (successMessage) toast.success(successMessage)
      return result
    } catch (error) {
      toast.error(errorText(error, failureMessage))
      return null
    } finally {
      setBusy(false)
    }
  }

  const handleSave = async () => {
    const urlChanged = showUrl && baseUrl.trim() !== ''
    if (!apiKey && !urlChanged) {
      toast.error('Enter a key to save')
      return
    }
    const saved = await run(
      () =>
        settingsAPI.saveProvider(provider, {
          apiKey: apiKey || undefined,
          baseUrl: urlChanged ? baseUrl.trim() : undefined,
        }),
      'Saved',
      'Could not save'
    )
    if (saved) {
      setApiKey('')
      setBaseUrl('')
      // The server now holds it, so drop any older copy kept in this browser.
      clearLegacy(provider)
      setLegacy({ apiKey: '', baseUrl: '' })
      onChanged?.()
    }
  }

  const handleTest = async () => {
    const result = await run(() => settingsAPI.testProvider(provider), null, 'Test failed')
    if (!result) return
    if (result.ok) toast.success(result.detail || 'Connection works')
    else toast.error(result.detail || 'Connection failed')
  }

  const handleRemove = async () => {
    const done = await run(() => settingsAPI.deleteProvider(provider), 'Key removed', 'Could not remove')
    if (done !== null) onChanged?.()
  }

  const handleMove = async () => {
    const saved = await run(
      () =>
        settingsAPI.saveProvider(provider, {
          apiKey: legacy.apiKey || undefined,
          baseUrl: showUrl && legacy.baseUrl ? legacy.baseUrl : undefined,
        }),
      'Moved to the server',
      'Could not move the key'
    )
    if (saved) {
      clearLegacy(provider)
      setLegacy({ apiKey: '', baseUrl: '' })
      onChanged?.()
    }
  }

  return (
    <div className="space-y-4 p-3 rounded-lg bg-white/5">
      {hasLegacy && (
        <div className="p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20 text-yellow-400 text-sm flex items-start gap-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-medium mb-1">A key is stored in this browser</p>
            <p>Move it to the server, where it is encrypted, and the browser copy is deleted.</p>
            <button
              type="button"
              onClick={handleMove}
              disabled={busy}
              className="mt-2 px-3 py-1 rounded-lg bg-yellow-500/20 hover:bg-yellow-500/30 disabled:opacity-50"
            >
              Move to server
            </button>
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 text-sm">
        {hasSavedKey && (
          <>
            <span className="px-2 py-0.5 rounded-full bg-green-400/20 text-green-400">Saved</span>
            <span className="font-mono text-gray-300">••••{status.key_hint}</span>
          </>
        )}
        {status?.source === 'server' && (
          <span className="text-gray-400">Using the server-wide key</span>
        )}
        {status?.needs_reentry && (
          <span className="text-yellow-400">
            The saved key can no longer be read. Enter it again.
          </span>
        )}
      </div>

      {showUrl && (
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">Ollama API URL</label>
          <input
            type="text"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            className="glass-input w-full"
            placeholder={status?.base_url || 'http://localhost:11434'}
            autoComplete="off"
          />
        </div>
      )}

      <div>
        <label className="block text-sm font-medium text-gray-300 mb-2">
          {hasSavedKey ? 'Replace key' : 'API key'}
        </label>
        <div className="relative">
          <Key className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={placeholder}
            className="glass-input w-full pl-10"
            autoComplete="new-password"
          />
        </div>
        <p className="mt-1 text-xs text-gray-500">
          Stored encrypted on the server and never shown again.{' '}
          {helpUrl && (
            <a
              href={helpUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-400 hover:text-blue-300 inline-flex items-center gap-1"
            >
              {helpLabel} <ExternalLink className="w-3 h-3" />
            </a>
          )}
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={handleSave}
          disabled={busy}
          className="glass-button-primary px-4 py-2 flex items-center gap-2 justify-center flex-1 disabled:opacity-50"
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          Save
        </button>
        <button
          type="button"
          onClick={handleTest}
          disabled={busy}
          className="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 flex items-center gap-2 disabled:opacity-50"
        >
          <Zap className="w-4 h-4" />
          Test
        </button>
        {hasSavedKey && (
          <button
            type="button"
            onClick={handleRemove}
            disabled={busy}
            className="px-4 py-2 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 flex items-center gap-2 disabled:opacity-50"
          >
            <Trash2 className="w-4 h-4" />
            Remove
          </button>
        )}
      </div>
    </div>
  )
}
