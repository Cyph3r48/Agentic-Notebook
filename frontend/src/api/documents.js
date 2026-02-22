import apiClient from './client'

export const documentsAPI = {
  // Upload a document
  upload: async (file, onProgress) => {
    const formData = new FormData()
    formData.append('file', file)

    const response = await apiClient.post('/documents/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress: onProgress
        ? (progressEvent) => {
            const percentCompleted = Math.round(
              (progressEvent.loaded * 100) / progressEvent.total
            )
            onProgress(percentCompleted)
          }
        : undefined,
    })
    return response.data
  },

  // List all documents for the current user
  list: async () => {
    const response = await apiClient.get('/documents')
    return response.data
  },

  // Get a single document by ID
  get: async (documentId) => {
    const response = await apiClient.get(`/documents/${documentId}`)
    return response.data
  },

  // Delete a document
  delete: async (documentId) => {
    await apiClient.delete(`/documents/${documentId}`)
  },

  // Retry processing a failed document
  retry: async (documentId) => {
    const response = await apiClient.post(`/documents/${documentId}/retry`)
    return response.data
  },
}
