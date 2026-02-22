import { create } from 'zustand'
import { persist } from 'zustand/middleware'

const useAuthStore = create(
  persist(
    (set, get) => ({
      // State
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,

      // Actions
      setUser: (user) => set({ user, isAuthenticated: !!user }),
      
      setTokens: (accessToken, refreshToken) => set({ 
        accessToken, 
        refreshToken,
        isAuthenticated: !!accessToken 
      }),
      
      setLoading: (isLoading) => set({ isLoading }),
      
      setError: (error) => set({ error }),
      
      clearError: () => set({ error: null }),
      
      logout: () => set({ 
        user: null, 
        accessToken: null, 
        refreshToken: null, 
        isAuthenticated: false,
        error: null 
      }),
      
      // Getters
      getAccessToken: () => get().accessToken,
      getRefreshToken: () => get().refreshToken,
      
      // Check if token is expired (basic check)
      isTokenExpired: () => {
        const token = get().accessToken
        if (!token) return true
        
        try {
          const payload = JSON.parse(atob(token.split('.')[1]))
          return payload.exp * 1000 < Date.now()
        } catch {
          return true
        }
      }
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({ 
        user: state.user,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        isAuthenticated: state.isAuthenticated 
      }),
    }
  )
)

export { useAuthStore }
