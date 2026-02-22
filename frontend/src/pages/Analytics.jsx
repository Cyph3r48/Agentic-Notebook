import { motion } from 'framer-motion'
import { 
  FileText, 
  MessageSquare, 
  Database, 
  Activity,
  Clock,
  CheckCircle,
  AlertCircle,
  Loader2,
  TrendingUp,
  BarChart3,
  PieChart
} from 'lucide-react'
import { useAnalytics } from '../hooks/useAnalytics'
import { formatDistanceToNow, formatFileSize } from '../lib/utils'

// Stat card component
const StatCard = ({ title, value, subtitle, icon: Icon, color, trend }) => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    whileHover={{ scale: 1.02 }}
    className="glass-card p-6"
  >
    <div className="flex items-start justify-between">
      <div className="flex-1">
        <p className="text-gray-400 text-sm mb-1">{title}</p>
        <p className="text-3xl font-bold text-white">{value}</p>
        {subtitle && <p className="text-sm text-gray-500 mt-1">{subtitle}</p>}
        {trend && (
          <div className="flex items-center gap-1 mt-2 text-green-400 text-sm">
            <TrendingUp className="w-4 h-4" />
            {trend}
          </div>
        )}
      </div>
      <div className={`p-3 rounded-xl ${color}`}>
        <Icon className="w-6 h-6 text-white" />
      </div>
    </div>
  </motion.div>
)

// Document status breakdown
const DocumentStatusChart = ({ stats }) => {
  const total = stats.totalDocuments || 1
  const completed = stats.completedDocuments || 0
  const processing = stats.processingDocuments || 0
  const failed = stats.failedDocuments || 0

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-6"
    >
      <div className="flex items-center gap-3 mb-6">
        <PieChart className="w-5 h-5 text-blue-400" />
        <h3 className="font-semibold">Document Status</h3>
      </div>

      <div className="space-y-4">
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-gray-400 flex items-center gap-2">
              <CheckCircle className="w-4 h-4 text-green-400" /> Completed
            </span>
            <span className="font-medium">{completed} ({Math.round((completed / total) * 100)}%)</span>
          </div>
          <div className="h-2 bg-white/10 rounded-full overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${(completed / total) * 100}%` }}
              className="h-full bg-green-400 rounded-full"
              transition={{ duration: 0.5 }}
            />
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-gray-400 flex items-center gap-2">
              <Loader2 className="w-4 h-4 text-yellow-400" /> Processing
            </span>
            <span className="font-medium">{processing} ({Math.round((processing / total) * 100)}%)</span>
          </div>
          <div className="h-2 bg-white/10 rounded-full overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${(processing / total) * 100}%` }}
              className="h-full bg-yellow-400 rounded-full"
              transition={{ duration: 0.5 }}
            />
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-gray-400 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-red-400" /> Failed
            </span>
            <span className="font-medium">{failed} ({Math.round((failed / total) * 100)}%)</span>
          </div>
          <div className="h-2 bg-white/10 rounded-full overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${(failed / total) * 100}%` }}
              className="h-full bg-red-400 rounded-full"
              transition={{ duration: 0.5 }}
            />
          </div>
        </div>
      </div>
    </motion.div>
  )
}

// Recent activity list
const RecentActivity = ({ title, items, type }) => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    className="glass-card p-6"
  >
    <div className="flex items-center gap-3 mb-4">
      <BarChart3 className="w-5 h-5 text-purple-400" />
      <h3 className="font-semibold">{title}</h3>
    </div>

    {items.length === 0 ? (
      <p className="text-gray-500 text-sm">No {type} in the last 7 days</p>
    ) : (
      <div className="space-y-3">
        {items.slice(0, 5).map((item) => (
          <div key={item.id} className="flex items-center gap-3 p-3 rounded-lg bg-white/5">
            <div className="w-8 h-8 rounded-lg bg-white/10 flex items-center justify-center">
              {type === 'conversations' ? (
                <MessageSquare className="w-4 h-4 text-blue-400" />
              ) : (
                <FileText className="w-4 h-4 text-green-400" />
              )}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">
                {item.title || item.original_filename || 'Untitled'}
              </p>
              <p className="text-xs text-gray-500">
                {formatDistanceToNow(item.updated_at || item.created_at)} ago
              </p>
            </div>
          </div>
        ))}
      </div>
    )}
  </motion.div>
)

// Main Analytics page
export const Analytics = () => {
  const { stats, recentConversations, recentDocuments, systemStatus, isLoading, isError } = useAnalytics()

  if (isLoading) {
    return (
      <div className="p-8">
        <div className="max-w-6xl mx-auto flex items-center justify-center py-20">
          <Loader2 className="w-8 h-8 text-blue-400 animate-spin" />
        </div>
      </div>
    )
  }

  if (isError) {
    return (
      <div className="p-8">
        <div className="max-w-6xl mx-auto">
          <div className="glass-card p-8 text-center">
            <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-4" />
            <h3 className="text-xl font-semibold mb-2">Failed to load analytics</h3>
            <p className="text-gray-400">Please try refreshing the page</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="p-8">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="max-w-6xl mx-auto"
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-4xl font-display font-bold text-gradient mb-2">
              Analytics
            </h1>
            <p className="text-gray-400">
              Track your usage and document insights
            </p>
          </div>
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <Clock className="w-4 h-4" />
            Last updated: {stats.lastActivity ? formatDistanceToNow(stats.lastActivity) + ' ago' : 'Never'}
          </div>
        </div>

        {/* Stats grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <StatCard
            title="Total Documents"
            value={stats.totalDocuments}
            subtitle={`${stats.completedDocuments} ready for chat`}
            icon={FileText}
            color="bg-blue-500"
            trend={recentDocuments.length > 0 ? `+${recentDocuments.length} this week` : null}
          />
          
          <StatCard
            title="Conversations"
            value={stats.totalConversations}
            subtitle="Active chat sessions"
            icon={MessageSquare}
            color="bg-purple-500"
            trend={recentConversations.length > 0 ? `+${recentConversations.length} this week` : null}
          />
          
          <StatCard
            title="Storage Used"
            value={formatFileSize(stats.storageUsed)}
            subtitle="Across all documents"
            icon={Database}
            color="bg-green-500"
          />
          
          <StatCard
            title="Activity"
            value={stats.totalMessages}
            subtitle={
              stats.sampledConversationTotal > stats.sampledConversations
                ? `Messages from ${stats.sampledConversations} most recent conversations`
                : 'Total messages exchanged'
            }
            icon={Activity}
            color="bg-orange-500"
          />
        </div>

        {/* Charts and activity */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {stats.totalDocuments > 0 && (
            <DocumentStatusChart stats={stats} />
          )}
          
          <RecentActivity 
            title="Recent Conversations"
            items={recentConversations}
            type="conversations"
          />
          
          <RecentActivity 
            title="Recent Documents"
            items={recentDocuments}
            type="documents"
          />
          
          <div className="glass-card p-6">
            <div className="flex items-center gap-3 mb-4">
              <Activity className="w-5 h-5 text-green-400" />
              <h3 className="font-semibold">System Status</h3>
            </div>
            
            <div className="space-y-3">
              <div className="flex items-center justify-between p-3 rounded-lg bg-white/5">
                <span className="text-sm text-gray-400">API Status</span>
                {systemStatus?.status === 'ok' ? (
                  <span className="flex items-center gap-2 text-sm text-green-400">
                    <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
                    Online
                  </span>
                ) : (
                  <span className="flex items-center gap-2 text-sm text-red-400">
                    <span className="w-2 h-2 rounded-full bg-red-400 animate-pulse" />
                    Unreachable
                  </span>
                )}
              </div>
              
              <div className="flex items-center justify-between p-3 rounded-lg bg-white/5">
                <span className="text-sm text-gray-400">Document Processing</span>
                <span className="text-sm">
                  {stats.processingDocuments > 0 ? (
                    <span className="text-yellow-400">{stats.processingDocuments} pending</span>
                  ) : (
                    <span className="text-green-400">Up to date</span>
                  )}
                </span>
              </div>
              
              <div className="flex items-center justify-between p-3 rounded-lg bg-white/5">
                <span className="text-sm text-gray-400">Failed Documents</span>
                <span className="text-sm">
                  {stats.failedDocuments > 0 ? (
                    <span className="text-red-400">{stats.failedDocuments} need attention</span>
                  ) : (
                    <span className="text-green-400">None</span>
                  )}
                </span>
              </div>
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  )
}
