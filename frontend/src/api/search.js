import apiClient from './client'

export const searchAPI = {
  // Search documents using semantic search
  search: async (query, options = {}) => {
    const { limit = 10, offset = 0, minScore = 0.1 } = options
    
    const response = await apiClient.post('/search', {
      query,
      limit,
      offset,
      min_score: minScore,
    })
    return response.data
  },

  // Quick search with default options
  quickSearch: async (query) => {
    return searchAPI.search(query, { limit: 5, minScore: 0.15 })
  },
}
