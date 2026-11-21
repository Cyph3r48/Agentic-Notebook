import apiClient from './client'

export const memoryAPI = {
  // Status of the document memory backend (vector search and embeddings).
  getHealth: async () => {
    const response = await apiClient.get('/memory/health')
    return response.data
  },
}
