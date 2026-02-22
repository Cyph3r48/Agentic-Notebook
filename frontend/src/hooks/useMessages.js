import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { chatAPI } from '../api/chat'
import { toast } from 'sonner'

// Query keys for messages
export const messageKeys = {
  all: ['messages'],
  lists: (conversationId) => ['messages', 'list', conversationId],
  detail: (messageId) => ['messages', 'detail', messageId],
}

export const useMessages = (conversationId) => {
  const queryClient = useQueryClient()

  // Query to fetch messages for a conversation
  const messagesQuery = useQuery({
    queryKey: messageKeys.lists(conversationId),
    queryFn: () => chatAPI.listMessages(conversationId, { limit: 100, sort: 'asc' }),
    enabled: !!conversationId,
    staleTime: 0, // Always fresh for chat
  })

  // Mutation to send a message (non-streaming)
  const sendMessageMutation = useMutation({
    mutationFn: async ({ content, useRag = true }) => {
      return chatAPI.sendMessage(conversationId, content, useRag)
    },
    onSuccess: () => {
      // Invalidate messages to fetch new ones
      queryClient.invalidateQueries({ 
        queryKey: messageKeys.lists(conversationId) 
      })
      // Also invalidate conversations to update last message timestamp
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
    },
    onError: (error) => {
      const message = error.response?.data?.detail || 'Failed to send message'
      toast.error(message)
    },
  })

  // Helper to add a message optimistically (for streaming)
  const addOptimisticMessage = (message) => {
    queryClient.setQueryData(
      messageKeys.lists(conversationId),
      (old) => {
        if (!old) return [message]
        return [...old, message]
      }
    )
  }

  // Helper to update an existing message
  const updateMessage = (messageId, updates) => {
    queryClient.setQueryData(
      messageKeys.lists(conversationId),
      (old) => {
        if (!old) return []
        return old.map((msg) =>
          msg.id === messageId ? { ...msg, ...updates } : msg
        )
      }
    )
  }

  return {
    // Queries
    messages: messagesQuery.data || [],
    isLoading: messagesQuery.isLoading,
    isError: messagesQuery.isError,
    error: messagesQuery.error,
    refetch: messagesQuery.refetch,

    // Mutations
    sendMessage: sendMessageMutation.mutateAsync,
    isSending: sendMessageMutation.isPending,

    // Helpers
    addOptimisticMessage,
    updateMessage,
  }
}
