import { AlertCircle, CheckCircle2, Database, Loader2, RefreshCw, XCircle } from 'lucide-react'
import { useMemoryHealth } from '../hooks/useMemoryHealth'

const STATUS = {
  ok: { label: 'Working', className: 'bg-green-400/20 text-green-400', Icon: CheckCircle2 },
  degraded: { label: 'Degraded', className: 'bg-yellow-400/20 text-yellow-400', Icon: AlertCircle },
  down: { label: 'Unavailable', className: 'bg-red-400/20 text-red-400', Icon: XCircle },
  disabled: { label: 'Off', className: 'bg-gray-400/20 text-gray-300', Icon: AlertCircle },
}

const COMPONENT_LABELS = {
  qdrant: 'Vector store (Qdrant)',
  embeddings: 'Embeddings (TEI)',
}

/** Shows whether document search is using vectors or has fallen back to keywords. */
export const MemoryStatusCard = () => {
  const { data, isLoading, isError, refetch, isFetching } = useMemoryHealth()
  const status = STATUS[data?.status] || STATUS.down

  return (
    <div className="p-4 rounded-lg bg-white/5">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <Database className="w-5 h-5 text-blue-400" />
          <div>
            <p className="font-medium">Document memory</p>
            <p className="text-sm text-gray-400">
              {data?.backend ? `Backend: ${data.backend}` : 'Where your uploaded documents are searched'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isLoading ? (
            <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
          ) : (
            <span className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm ${isError ? STATUS.down.className : status.className}`}>
              <status.Icon className="w-4 h-4" />
              {isError ? 'Unknown' : status.label}
            </span>
          )}
          <button
            type="button"
            onClick={() => refetch()}
            disabled={isFetching}
            className="p-2 rounded-lg bg-white/10 hover:bg-white/20 disabled:opacity-50"
            aria-label="Check again"
          >
            <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {isError && (
        <p className="text-sm text-yellow-400">Could not read the memory status. Is the backend running?</p>
      )}

      {data && (
        <div className="space-y-2">
          <p className="text-sm text-gray-300">{data.detail}</p>
          {Object.entries(data.components || {}).map(([name, part]) => (
            <div key={name} className="flex items-start gap-2 text-sm">
              {part.ok ? (
                <CheckCircle2 className="w-4 h-4 mt-0.5 text-green-400 flex-shrink-0" />
              ) : (
                <XCircle className="w-4 h-4 mt-0.5 text-red-400 flex-shrink-0" />
              )}
              <div>
                <span className="text-gray-200">{COMPONENT_LABELS[name] || name}</span>
                <span className="text-gray-500"> · {part.detail}</span>
              </div>
            </div>
          ))}
          {data.last_error && (
            <p className="text-xs text-gray-500">Last problem: {data.last_error}</p>
          )}
          {data.status === 'down' || data.status === 'degraded' ? (
            <p className="text-xs text-gray-500">
              Search still works with keywords. The first start downloads the embedding model, which can take a few minutes.
            </p>
          ) : null}
        </div>
      )}
    </div>
  )
}
