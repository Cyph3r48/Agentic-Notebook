import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { authAPI } from '../api/auth'
import { useAuthStore } from '../store/authStore'
import { toast } from 'sonner'

export const useAuth = () => {
  const queryClient = useQueryClient()
  const { setUser, setTokens, logout: logoutStore, setLoading, setError, clearError } = useAuthStore()

  // Get current user query
  const userQuery = useQuery({
    queryKey: ['user'],
    queryFn: async () => {
      const data = await authAPI.getMe()
      setUser(data)
      return data
    },
    enabled: useAuthStore.getState().isAuthenticated,
    retry: false,
  })

  // Login mutation
  const loginMutation = useMutation({
    mutationFn: async ({ email, password }) => {
      setLoading(true)
      clearError()
      try {
        const data = await authAPI.login(email, password)
        setTokens(data.access_token, data.refresh_token)
        
        // Fetch user info after login
        const user = await authAPI.getMe()
        setUser(user)
        
        return { success: true, user }
      } catch (error) {
        const message = error.response?.data?.detail || 'Login failed'
        setError(message)
        throw new Error(message)
      } finally {
        setLoading(false)
      }
    },
    onSuccess: () => {
      toast.success('Welcome back!')
      queryClient.invalidateQueries({ queryKey: ['user'] })
    },
    onError: (error) => {
      toast.error(error.message)
    },
  })

  // Logout mutation
  const logoutMutation = useMutation({
    mutationFn: async () => {
      const refreshToken = useAuthStore.getState().refreshToken
      if (refreshToken) {
        try {
          await authAPI.logout(refreshToken)
        } catch (error) {
          console.error('Logout error:', error)
        }
      }
      logoutStore()
      queryClient.clear()
    },
    onSuccess: () => {
      toast.success('Logged out successfully')
    },
  })

  return {
    // State
    user: useAuthStore((state) => state.user),
    isAuthenticated: useAuthStore((state) => state.isAuthenticated),
    isLoading: useAuthStore((state) => state.isLoading),
    error: useAuthStore((state) => state.error),
    
    // Queries
    userQuery,
    
    // Mutations
    login: loginMutation.mutateAsync,
    logout: logoutMutation.mutateAsync,
    isLoginLoading: loginMutation.isPending,
    isLogoutLoading: logoutMutation.isPending,
  }
}
