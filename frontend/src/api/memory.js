import apiClient from './client'

export const memoryAPI = {
  // Status of the document memory backend (vector search and embeddings).
  getHealth: async () => {
    const response = await apiClient.get('/memory/health')
    return response.data
  },

  // Re-embed every stored chunk with the active embedding model (admin). Runs in the background.
  startReindex: async () => {
    const response = await apiClient.post('/memory/reindex')
    return response.data
  },
}
