import apiClient from './client'

// Since there's no dedicated analytics endpoint yet, 
// we'll aggregate data from existing endpoints
export const analyticsAPI = {
  // Get system status
  getSystemStatus: async () => {
    const response = await apiClient.get('/system/ping')
    return response.data
  },

  // Get aggregated stats (computed on frontend from other endpoints)
  // This will be replaced with a real endpoint when backend analytics is built
  getStats: async () => {
    // For now, return placeholder - real implementation will aggregate
    // from documents, conversations, and messages endpoints
    return {
      totalDocuments: 0,
      totalConversations: 0,
      totalMessages: 0,
      storageUsed: 0,
      lastActivity: null,
    }
  },
}
