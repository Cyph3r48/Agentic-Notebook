import apiClient, { API_BASE_URL } from '../api/client'

export async function* streamConversationMessage(conversationId, content, useRag = false, token) {
  const base = (apiClient.defaults.baseURL || API_BASE_URL || '').replace(/\/+$/, '')
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
    throw new Error(`Stream request failed (${response.status}): ${body}`)
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
      yield { type: event, data: parsed }
    }
  }
}

function withAuth(headers, token) {
  if (!token) return headers
  return {
    ...headers,
    Authorization: `Bearer ${token}`,
  }
}
