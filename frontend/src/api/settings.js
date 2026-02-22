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

  // Placeholder for when backend adds update endpoints
  // updateProfile: async (data) => {
  //   const response = await apiClient.patch('/users/me', data)
  //   return response.data
  // },
  //
  // changePassword: async (oldPassword, newPassword) => {
  //   const response = await apiClient.post('/auth/change-password', {
  //     old_password: oldPassword,
  //     new_password: newPassword,
  //   })
  //   return response.data
  // },
}
