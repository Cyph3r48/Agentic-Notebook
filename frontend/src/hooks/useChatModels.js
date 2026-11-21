import { useQuery } from '@tanstack/react-query'
import { chatAPI } from '../api/chat'

export const useChatModels = (token) => {
  return useQuery({
    queryKey: ['chat-models'],
    queryFn: chatAPI.getModels,
    enabled: !!token,
    staleTime: 5 * 60 * 1000, // 5 minutes
  })
}

// The Settings page calls this without a token, and the API client attaches the login token itself, so
// the query must not wait for one (it used to stay disabled and every badge read "not configured").
export const useProviderHealth = () => {
  return useQuery({
    queryKey: ['provider-health'],
    queryFn: chatAPI.getProviderHealth,
    staleTime: 30 * 1000, // 30 seconds
  })
}

// Hook to get models from the regular API (for model selection dropdown)
export const useModels = () => {
  return useQuery({
    queryKey: ['models'],
    queryFn: async () => {
      const data = await chatAPI.getModels()
      return data
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
  })
}
