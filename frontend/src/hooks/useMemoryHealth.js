import { useQuery } from '@tanstack/react-query'
import { memoryAPI } from '../api/memory'

export const useMemoryHealth = () => {
  return useQuery({
    queryKey: ['memory-health'],
    queryFn: memoryAPI.getHealth,
    staleTime: 30 * 1000,
    refetchOnWindowFocus: true,
  })
}
