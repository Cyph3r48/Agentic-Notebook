import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { embeddingAPI } from '../api/embedding'
import { memoryAPI } from '../api/memory'

const errorText = (error, fallback) => {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg
  return error?.response?.data?.message || fallback
}

export const useEmbeddingSettings = () => {
  return useQuery({
    queryKey: ['embedding-settings'],
    queryFn: embeddingAPI.getSettings,
    staleTime: 30 * 1000,
  })
}

export const useTestEmbedding = () => useMutation({ mutationFn: embeddingAPI.test })

export const useApplyEmbedding = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: embeddingAPI.apply,
    onSuccess: (data) => {
      queryClient.setQueryData(['embedding-settings'], data)
      queryClient.invalidateQueries({ queryKey: ['memory-health'] })
      toast.success('Embedding model saved. Re-index your documents to use it.')
    },
    onError: (error) => toast.error(errorText(error, 'Could not save the embedding model')),
  })
}

export const useStartReindex = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: memoryAPI.startReindex,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memory-health'] })
      toast.success('Re-indexing started')
    },
    onError: (error) => toast.error(errorText(error, 'Could not start re-indexing')),
  })
}
