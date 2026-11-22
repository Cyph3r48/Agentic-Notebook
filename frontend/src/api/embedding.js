import apiClient from './client'

// The embedding model for the whole system. Anyone signed in can read it; only an admin can test or change it.
// Responses never contain a key, only a short hint.
const body = ({ provider, model, baseUrl, apiKey, clearKey }) => {
  const payload = { provider }
  if (model) payload.model = model
  if (baseUrl) payload.base_url = baseUrl
  if (apiKey) payload.api_key = apiKey
  if (clearKey) payload.clear_key = true
  return payload
}

export const embeddingAPI = {
  getSettings: async () => {
    const response = await apiClient.get('/settings/embedding')
    return response.data
  },

  // Really embeds a test string and reports the vector size. Saves nothing.
  test: async (candidate) => {
    const response = await apiClient.post('/settings/embedding/test', body(candidate))
    return response.data
  },

  // Saved only if the same probe succeeds.
  apply: async (candidate) => {
    const response = await apiClient.put('/settings/embedding', body(candidate))
    return response.data
  },
}
