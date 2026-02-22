import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { documentsAPI } from '../api/documents'
import { toast } from 'sonner'

// Query keys for documents
export const documentKeys = {
  all: ['documents'],
  lists: () => [...documentKeys.all, 'list'],
  list: (filters) => [...documentKeys.lists(), { filters }],
  details: () => [...documentKeys.all, 'detail'],
  detail: (id) => [...documentKeys.details(), id],
}

export const useDocuments = () => {
  const queryClient = useQueryClient()

  // Query to fetch all documents
  const documentsQuery = useQuery({
    queryKey: documentKeys.lists(),
    queryFn: documentsAPI.list,
    staleTime: 30 * 1000, // 30 seconds
  })

  // Query to fetch a single document
  const useDocument = (documentId) =>
    useQuery({
      queryKey: documentKeys.detail(documentId),
      queryFn: () => documentsAPI.get(documentId),
      enabled: !!documentId,
    })

  // Mutation to upload a document
  const uploadMutation = useMutation({
    mutationFn: async ({ file, onProgress }) => {
      return documentsAPI.upload(file, onProgress)
    },
    onSuccess: (data) => {
      toast.success(`Document "${data.filename}" uploaded successfully`)
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() })
    },
    onError: (error) => {
      const message = error.response?.data?.detail || 'Failed to upload document'
      toast.error(message)
    },
  })

  // Mutation to delete a document
  const deleteMutation = useMutation({
    mutationFn: documentsAPI.delete,
    onSuccess: () => {
      toast.success('Document deleted successfully')
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() })
    },
    onError: (error) => {
      const message = error.response?.data?.detail || 'Failed to delete document'
      toast.error(message)
    },
  })

  // Mutation to retry processing
  const retryMutation = useMutation({
    mutationFn: documentsAPI.retry,
    onSuccess: (data) => {
      toast.success(`Processing retry initiated for "${data.filename}"`)
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() })
      queryClient.invalidateQueries({ queryKey: documentKeys.detail(data.id) })
    },
    onError: (error) => {
      const message = error.response?.data?.detail || 'Failed to retry processing'
      toast.error(message)
    },
  })

  return {
    // Queries
    documents: documentsQuery.data || [],
    isLoading: documentsQuery.isLoading,
    isError: documentsQuery.isError,
    error: documentsQuery.error,
    refetch: documentsQuery.refetch,
    useDocument,

    // Mutations
    uploadDocument: uploadMutation.mutateAsync,
    isUploading: uploadMutation.isPending,
    uploadProgress: uploadMutation.progress,

    deleteDocument: deleteMutation.mutateAsync,
    isDeleting: deleteMutation.isPending,

    retryProcessing: retryMutation.mutateAsync,
    isRetrying: retryMutation.isPending,
  }
}
