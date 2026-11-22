import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { modelsAPI } from '../api/models'

export const useModelSettings = () => {
  return useQuery({
    queryKey: ['model-settings'],
    queryFn: modelsAPI.getSettings,
    staleTime: 30 * 1000,
  })
}

export const useSaveModelSettings = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: modelsAPI.saveSettings,
    onSuccess: (data) => {
      queryClient.setQueryData(['model-settings'], data)
      // The chat list is the enabled subset, so it has to be fetched again.
      queryClient.invalidateQueries({ queryKey: ['models'] })
      queryClient.invalidateQueries({ queryKey: ['chat-models'] })
      toast.success('Models saved')
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || error.response?.data?.message || 'Could not save models')
    },
  })
}
