import { useQuery } from '@tanstack/react-query'
import { useDocuments } from './useDocuments'
import { useConversations } from './useConversations'
import { analyticsAPI } from '../api/analytics'
import { chatAPI } from '../api/chat'

export const useAnalytics = () => {
  // Get data from existing hooks
  const { documents, isLoading: isLoadingDocs, isError: isDocsError } = useDocuments()
  const { conversations, isLoading: isLoadingConvs, isError: isConversationsError } = useConversations()

  // System status query
  const systemStatusQuery = useQuery({
    queryKey: ['system-status'],
    queryFn: analyticsAPI.getSystemStatus,
    staleTime: 60 * 1000, // 1 minute
  })

  // Message counts query (sample recent conversations to avoid excessive API calls)
  const messageStatsQuery = useQuery({
    queryKey: ['analytics-message-stats', conversations?.map((c) => c.id) || []],
    enabled: Array.isArray(conversations) && conversations.length > 0,
    staleTime: 60 * 1000,
    queryFn: async () => {
      const sorted = [...conversations].sort(
        (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
      )
      const sampled = sorted.slice(0, 20)
      const counts = await Promise.all(
        sampled.map(async (conv) => {
          try {
            const rows = await chatAPI.listMessages(conv.id, { limit: 200, sort: 'asc' })
            return rows.length
          } catch {
            return 0
          }
        })
      )

      return {
        totalMessages: counts.reduce((acc, count) => acc + count, 0),
        sampledConversations: sampled.length,
        totalConversations: conversations.length,
      }
    },
  })

  // Calculate aggregated stats
  const stats = {
    totalDocuments: documents?.length || 0,
    totalConversations: conversations?.length || 0,
    totalMessages: messageStatsQuery.data?.totalMessages || 0,
    storageUsed: documents?.reduce((acc, doc) => acc + (doc.file_size || 0), 0) || 0,
    processingDocuments: documents?.filter(d => d.status === 'pending').length || 0,
    failedDocuments: documents?.filter(d => d.status === 'failed').length || 0,
    completedDocuments: documents?.filter(d => d.status === 'completed').length || 0,
    lastActivity: conversations?.[0]?.updated_at || documents?.[0]?.created_at || null,
    sampledConversations: messageStatsQuery.data?.sampledConversations || 0,
    sampledConversationTotal: messageStatsQuery.data?.totalConversations || 0,
  }

  // Recent activity (last 7 days)
  const sevenDaysAgo = new Date()
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7)
  
  const recentConversations = conversations?.filter(
    c => new Date(c.updated_at) > sevenDaysAgo
  ) || []

  const recentDocuments = documents?.filter(
    d => new Date(d.created_at) > sevenDaysAgo
  ) || []

  return {
    stats,
    recentConversations,
    recentDocuments,
    systemStatus: systemStatusQuery.data,
    isLoading: isLoadingDocs || isLoadingConvs || systemStatusQuery.isLoading || messageStatsQuery.isLoading,
    isError: isDocsError || isConversationsError || systemStatusQuery.isError,
  }
}
