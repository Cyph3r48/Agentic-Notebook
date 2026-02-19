import { apiClient, withAuth } from './apiClient'

export async function fetchChatModels(token) {
  const { data } = await apiClient.get('/chat/models', {
    headers: withAuth({}, token),
  })
  return data
}

export async function fetchProviderHealth(token) {
  const { data } = await apiClient.get('/chat/providers/health', {
    headers: withAuth({}, token),
  })
  return data
}

export async function streamConversationMessage({
  token,
  conversationId,
  content,
  useRag = false,
  onDelta,
  onMessage,
  onDone,
  onError,
}) {
  const base = (apiClient.defaults.baseURL || '').replace(/\/+$/, '')
  const response = await fetch(`${base}/chat/conversations/${conversationId}/messages/stream`, {
    method: 'POST',
    headers: withAuth(
      {
        'Content-Type': 'application/json',
      },
      token
    ),
    body: JSON.stringify({
      content,
      use_rag: useRag,
    }),
  })

  if (!response.ok || !response.body) {
    const body = await response.text().catch(() => '')
    const error = new Error(`Stream request failed (${response.status}): ${body}`)
    if (onError) onError(error)
    throw error
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let splitIndex = buffer.indexOf('\n\n')
    while (splitIndex !== -1) {
      const rawEvent = buffer.slice(0, splitIndex)
      buffer = buffer.slice(splitIndex + 2)
      splitIndex = buffer.indexOf('\n\n')

      const lines = rawEvent.split('\n')
      const eventLine = lines.find((line) => line.startsWith('event: '))
      const dataLine = lines.find((line) => line.startsWith('data: '))
      if (!eventLine || !dataLine) continue

      const event = eventLine.slice('event: '.length).trim()
      const rawData = dataLine.slice('data: '.length).trim()

      let parsed = {}
      try {
        parsed = rawData ? JSON.parse(rawData) : {}
      } catch {
        parsed = { raw: rawData }
      }

      if (event === 'delta' && onDelta) onDelta(parsed)
      if (event === 'message' && onMessage) onMessage(parsed)
      if (event === 'done' && onDone) onDone(parsed)
    }
  }

  return true
}

