// How each provider is shown. The server decides which providers exist and which have models for a user;
// this only holds labels and colours, in display order.
export const MODEL_GROUPS = [
  { key: 'ollama', label: 'Local Models (Ollama)', selectedClass: 'bg-blue-500/20 text-blue-400' },
  { key: 'ollama_cloud', label: 'Ollama Cloud', selectedClass: 'bg-purple-500/20 text-purple-400' },
  { key: 'anthropic', label: 'Claude API', selectedClass: 'bg-orange-500/20 text-orange-400' },
  { key: 'openai', label: 'OpenAI', selectedClass: 'bg-green-500/20 text-green-400' },
]

// Two providers can list the same model name (a local and a cloud Ollama), so a choice is always provider plus id.
export const modelKey = (provider, id) => `${provider}:${id}`
