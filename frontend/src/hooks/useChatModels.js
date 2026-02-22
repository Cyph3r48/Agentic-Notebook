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

export const useProviderHealth = (token) => {
  return useQuery({
    queryKey: ['provider-health'],
    queryFn: chatAPI.getProviderHealth,
    enabled: !!token,
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
