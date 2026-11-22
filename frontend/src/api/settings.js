import apiClient from './client'

export const settingsAPI = {
  // Get current user info (already in auth.js, but good to have here for consistency)
  getCurrentUser: async () => {
    const response = await apiClient.get('/auth/me')
    return response.data
  },

  getSystemStatus: async () => {
    const response = await apiClient.get('/system/ping')
    return response.data
  },

  // Provider keys live on the server, encrypted. Responses never contain a key, only a short hint.
  listProviders: async () => {
    const response = await apiClient.get('/settings/providers')
    return response.data
  },

  saveProvider: async (provider, { apiKey, baseUrl } = {}) => {
    const body = {}
    if (apiKey) body.api_key = apiKey
    if (baseUrl !== undefined) body.base_url = baseUrl
    const response = await apiClient.put(`/settings/providers/${provider}`, body)
    return response.data
  },

  deleteProvider: async (provider) => {
    await apiClient.delete(`/settings/providers/${provider}`)
  },

  testProvider: async (provider) => {
    const response = await apiClient.post(`/settings/providers/${provider}/test`)
    return response.data
  },

  // Change your display name. Email and username cannot be changed.
  updateProfile: async (fullName) => {
    const response = await apiClient.patch('/users/me', { full_name: fullName })
    return response.data
  },

  // Change your password. Other devices are signed out; the response holds fresh tokens for this one.
  changePassword: async (currentPassword, newPassword) => {
    const response = await apiClient.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    })
    return response.data
  },
}
