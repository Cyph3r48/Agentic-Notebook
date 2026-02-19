import { useQuery } from '@tanstack/react-query'

import { fetchChatModels, fetchProviderHealth } from '../lib/chatApi'

export function useChatModels(token) {
  return useQuery({
    queryKey: ['chat-models'],
    queryFn: () => fetchChatModels(token),
    enabled: Boolean(token),
    staleTime: 60 * 1000,
    refetchInterval: 60 * 1000,
  })
}

export function useProviderHealth(token) {
  return useQuery({
    queryKey: ['chat-provider-health'],
    queryFn: () => fetchProviderHealth(token),
    enabled: Boolean(token),
    staleTime: 15 * 1000,
    refetchInterval: 15 * 1000,
  })
}

