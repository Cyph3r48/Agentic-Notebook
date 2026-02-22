import apiClient from './client'

export const authAPI = {
  // Login with email and password
  login: async (email, password) => {
    const response = await apiClient.post('/auth/login', {
      email,
      password,
    })
    return response.data
  },

  // Get current user info
  getMe: async () => {
    const response = await apiClient.get('/auth/me')
    return response.data
  },

  // Refresh access token
  refresh: async (refreshToken) => {
    const response = await apiClient.post('/auth/refresh', {
      refresh_token: refreshToken,
    })
    return response.data
  },

  // Logout (invalidate refresh token)
  logout: async (refreshToken) => {
    await apiClient.post('/auth/logout', {
      refresh_token: refreshToken,
    })
  },
}
