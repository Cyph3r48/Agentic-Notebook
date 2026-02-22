import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { chatAPI } from '../api/chat'
import { toast } from 'sonner'

// Query keys for conversations
export const conversationKeys = {
  all: ['conversations'],
  lists: () => [...conversationKeys.all, 'list'],
  list: (filters) => [...conversationKeys.lists(), { filters }],
  details: () => [...conversationKeys.all, 'detail'],
  detail: (id) => [...conversationKeys.details(), id],
}

export const useConversations = () => {
  const queryClient = useQueryClient()

  // Query to fetch all conversations
  const conversationsQuery = useQuery({
    queryKey: conversationKeys.lists(),
    queryFn: () => chatAPI.listConversations({ limit: 100 }),
    staleTime: 30 * 1000, // 30 seconds
  })

  // Query to fetch a single conversation
  const useConversation = (conversationId) =>
    useQuery({
      queryKey: conversationKeys.detail(conversationId),
      queryFn: () => chatAPI.getConversation(conversationId),
      enabled: !!conversationId,
    })

  // Mutation to create a conversation
  const createMutation = useMutation({
    mutationFn: async ({ title, model }) => {
      return chatAPI.createConversation(title, model)
    },
    onSuccess: () => {
      toast.success('Conversation created')
      queryClient.invalidateQueries({ queryKey: conversationKeys.lists() })
    },
    onError: (error) => {
      const message = error.response?.data?.detail || 'Failed to create conversation'
      toast.error(message)
    },
  })

  // Mutation to update a conversation
  const updateMutation = useMutation({
    mutationFn: async ({ conversationId, title }) => {
      return chatAPI.updateConversation(conversationId, title)
    },
    onSuccess: (data) => {
      toast.success('Conversation updated')
      queryClient.invalidateQueries({ queryKey: conversationKeys.lists() })
      queryClient.invalidateQueries({ queryKey: conversationKeys.detail(data.id) })
    },
    onError: (error) => {
      const message = error.response?.data?.detail || 'Failed to update conversation'
      toast.error(message)
    },
  })

  // Mutation to delete a conversation
  const deleteMutation = useMutation({
    mutationFn: chatAPI.deleteConversation,
    onSuccess: () => {
      toast.success('Conversation deleted')
      queryClient.invalidateQueries({ queryKey: conversationKeys.lists() })
    },
    onError: (error) => {
      const message = error.response?.data?.detail || 'Failed to delete conversation'
      toast.error(message)
    },
  })

  return {
    // Queries
    conversations: conversationsQuery.data || [],
    isLoading: conversationsQuery.isLoading,
    isError: conversationsQuery.isError,
    error: conversationsQuery.error,
    refetch: conversationsQuery.refetch,
    useConversation,

    // Mutations
    createConversation: createMutation.mutateAsync,
    isCreating: createMutation.isPending,

    updateConversation: updateMutation.mutateAsync,
    isUpdating: updateMutation.isPending,

    deleteConversation: deleteMutation.mutateAsync,
    isDeleting: deleteMutation.isPending,
  }
}
