import apiClient from './client'

export const chatAPI = {
  // Create a new conversation
  createConversation: async (title, model) => {
    const response = await apiClient.post('/chat/conversations', {
      title,
      model,
    })
    return response.data
  },

  // List all conversations
  listConversations: async (params = {}) => {
    const response = await apiClient.get('/chat/conversations', { params })
    return response.data
  },

  // Get a single conversation
  getConversation: async (conversationId) => {
    const response = await apiClient.get(`/chat/conversations/${conversationId}`)
    return response.data
  },

  // Update conversation (title)
  updateConversation: async (conversationId, title) => {
    const response = await apiClient.patch(`/chat/conversations/${conversationId}`, {
      title,
    })
    return response.data
  },

  // Delete a conversation
  deleteConversation: async (conversationId) => {
    await apiClient.delete(`/chat/conversations/${conversationId}`)
  },

  // Send a message (non-streaming)
  sendMessage: async (conversationId, content, useRag = true) => {
    const response = await apiClient.post(`/chat/conversations/${conversationId}/messages`, {
      content,
      use_rag: useRag,
    })
    return response.data
  },

  // List messages in a conversation
  listMessages: async (conversationId, params = {}) => {
    const response = await apiClient.get(`/chat/conversations/${conversationId}/messages`, { params })
    return response.data
  },

  // Get available models
  getModels: async () => {
    const response = await apiClient.get('/chat/models')
    return response.data
  },

  // Get provider health status
  getProviderHealth: async () => {
    const response = await apiClient.get('/chat/providers/health')
    return response.data
  },
}
