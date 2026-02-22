import { useQuery, useMutation } from '@tanstack/react-query'
import { searchAPI } from '../api/search'
import { toast } from 'sonner'

// Query keys for search
export const searchKeys = {
  all: ['search'],
  results: (query) => [...searchKeys.all, 'results', query],
}

export const useSearch = () => {
  // Query for search results (enabled only when query is provided)
  const useSearchResults = (query, options = {}) => {
    return useQuery({
      queryKey: searchKeys.results(query),
      queryFn: () => searchAPI.search(query, options),
      enabled: !!query && query.trim().length > 0,
      staleTime: 5 * 60 * 1000, // 5 minutes
    })
  }

  // Mutation for quick search
  const quickSearchMutation = useMutation({
    mutationFn: ({ query }) => searchAPI.quickSearch(query),
    onError: (error) => {
      const message = error.response?.data?.detail || 'Search failed'
      toast.error(message)
    },
  })

  return {
    useSearchResults,
    quickSearch: quickSearchMutation.mutateAsync,
    isQuickSearching: quickSearchMutation.isPending,
    quickSearchResults: quickSearchMutation.data,
  }
}
