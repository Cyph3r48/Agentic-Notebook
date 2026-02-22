import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { 
  FileText, 
  MessageSquare, 
  Database, 
  Upload, 
  Plus, 
  ArrowRight,
  Sparkles,
  BookOpen,
  Search,
  Clock
} from 'lucide-react'
import { useDocuments } from '../hooks/useDocuments'
import { useConversations } from '../hooks/useConversations'
import { useAuth } from '../hooks/useAuth'
import { formatFileSize, formatDistanceToNow } from '../lib/utils'

// Stat card component with real data
const StatCard = ({ title, value, subtitle, icon: Icon, color, onClick }) => (
  <motion.div
    whileHover={{ scale: 1.02 }}
    onClick={onClick}
    className={`glass-card p-6 ${onClick ? 'cursor-pointer' : ''}`}
  >
    <div className="flex items-start justify-between">
      <div className="flex-1">
        <p className="text-gray-400 text-sm mb-1">{title}</p>
        <p className="text-3xl font-bold text-white">{value}</p>
        {subtitle && <p className="text-sm text-gray-500 mt-1">{subtitle}</p>}
      </div>
      <div className={`p-3 rounded-xl ${color}`}>
        <Icon className="w-6 h-6 text-white" />
      </div>
    </div>
  </motion.div>
)

// Quick action button
const QuickAction = ({ icon: Icon, title, description, onClick, primary }) => (
  <motion.button
    whileHover={{ scale: 1.02 }}
    whileTap={{ scale: 0.98 }}
    onClick={onClick}
    className={`
      glass-card p-5 text-left w-full transition-all
      ${primary ? 'border-blue-500/30 hover:border-blue-500/50' : 'hover:bg-white/5'}
    `}
  >
    <div className="flex items-start gap-4">
      <div className={`
        p-3 rounded-xl flex-shrink-0
        ${primary ? 'bg-blue-500/20' : 'bg-white/5'}
      `}
      >
        <Icon className={`w-5 h-5 ${primary ? 'text-blue-400' : 'text-gray-400'}`} />
      </div>
      <div className="flex-1">
        <h3 className="font-semibold mb-1 flex items-center gap-2">
          {title}
          <ArrowRight className="w-4 h-4 text-gray-500" />
        </h3>
        <p className="text-sm text-gray-400">{description}</p>
      </div>
    </div>
  </motion.button>
)

// Recent item component
const RecentItem = ({ type, title, timestamp, onClick }) => (
  <div
    onClick={onClick}
    className="flex items-center gap-3 p-3 rounded-lg hover:bg-white/5 cursor-pointer transition-colors"
  >
    <div className="w-10 h-10 rounded-lg bg-white/10 flex items-center justify-center flex-shrink-0">
      {type === 'document' ? (
        <FileText className="w-5 h-5 text-green-400" />
      ) : (
        <MessageSquare className="w-5 h-5 text-blue-400" />
      )}
    </div>
    <div className="flex-1 min-w-0">
      <p className="font-medium text-sm truncate">{title || 'Untitled'}</p>
      <p className="text-xs text-gray-500 flex items-center gap-1">
        <Clock className="w-3 h-3" />
        {formatDistanceToNow(timestamp)} ago
      </p>
    </div>
  </div>
)

export const Dashboard = () => {
  const navigate = useNavigate()
  const { user } = useAuth()
  const { documents, isLoading: isLoadingDocs } = useDocuments()
  const { conversations, isLoading: isLoadingConvs } = useConversations()

  // Calculate stats
  const stats = {
    totalDocuments: documents?.length || 0,
    totalConversations: conversations?.length || 0,
    storageUsed: documents?.reduce((acc, doc) => acc + (doc.file_size || 0), 0) || 0,
    readyDocuments: documents?.filter(d => d.status === 'completed').length || 0,
  }

  // Get recent items (sorted by date)
  const recentDocuments = [...(documents || [])]
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
    .slice(0, 3)

  const recentConversations = [...(conversations || [])]
    .sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at))
    .slice(0, 3)

  return (
    <div className="p-8">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="max-w-6xl mx-auto"
      >
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-display font-bold text-gradient mb-2">
            Dashboard
          </h1>
          <p className="text-gray-400">
            Welcome back{user?.full_name ? `, ${user.full_name}` : ''}! Here&apos;s what&apos;s happening with your knowledge base.
          </p>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <StatCard
            title="Documents"
            value={isLoadingDocs ? '...' : stats.totalDocuments}
            subtitle={`${stats.readyDocuments} ready for chat`}
            icon={FileText}
            color="bg-green-500"
            onClick={() => navigate('/documents')}
          />
          
          <StatCard
            title="Conversations"
            value={isLoadingConvs ? '...' : stats.totalConversations}
            subtitle="Active chat sessions"
            icon={MessageSquare}
            color="bg-blue-500"
            onClick={() => navigate('/chat')}
          />
          
          <StatCard
            title="Storage Used"
            value={isLoadingDocs ? '...' : formatFileSize(stats.storageUsed)}
            subtitle="Across all documents"
            icon={Database}
            color="bg-purple-500"
          />
        </div>

        {/* Quick Actions */}
        <div className="mb-8">
          <h2 className="text-xl font-semibold mb-4">Quick Actions</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <QuickAction
              icon={Upload}
              title="Upload Document"
              description="Add PDF, DOCX, TXT, or MD files to your knowledge base"
              onClick={() => navigate('/documents')}
              primary
            />
            
            <QuickAction
              icon={Plus}
              title="New Conversation"
              description="Start chatting with AI powered by your documents"
              onClick={() => navigate('/chat')}
            />
            
            <QuickAction
              icon={Search}
              title="Search Documents"
              description="Find relevant content using semantic search"
              onClick={() => navigate('/documents')}
            />
            
            <QuickAction
              icon={BookOpen}
              title="View Analytics"
              description="Check your usage stats and document insights"
              onClick={() => navigate('/analytics')}
            />
          </div>
        </div>

        {/* Two column layout */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Recent Documents */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="glass-card p-6"
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold flex items-center gap-2">
                <FileText className="w-5 h-5 text-green-400" />
                Recent Documents
              </h3>
              <button
                onClick={() => navigate('/documents')}
                className="text-sm text-blue-400 hover:text-blue-300 flex items-center gap-1"
              >
                View all <ArrowRight className="w-4 h-4" />
              </button>
            </div>

            {recentDocuments.length === 0 ? (
              <div className="text-center py-8">
                <div className="w-12 h-12 rounded-xl bg-white/5 flex items-center justify-center mx-auto mb-3">
                  <Upload className="w-6 h-6 text-gray-500" />
                </div>
                <p className="text-gray-400 text-sm">No documents yet</p>
                <p className="text-gray-500 text-xs mt-1">Upload your first document to get started</p>
              </div>
            ) : (
              <div className="space-y-1">
                {recentDocuments.map((doc) => (
                  <RecentItem
                    key={doc.id}
                    type="document"
                    title={doc.original_filename}
                    timestamp={doc.created_at}
                    onClick={() => navigate('/documents')}
                  />
                ))}
              </div>
            )}
          </motion.div>

          {/* Recent Conversations */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="glass-card p-6"
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold flex items-center gap-2">
                <MessageSquare className="w-5 h-5 text-blue-400" />
                Recent Conversations
              </h3>
              <button
                onClick={() => navigate('/chat')}
                className="text-sm text-blue-400 hover:text-blue-300 flex items-center gap-1"
              >
                View all <ArrowRight className="w-4 h-4" />
              </button>
            </div>

            {recentConversations.length === 0 ? (
              <div className="text-center py-8">
                <div className="w-12 h-12 rounded-xl bg-white/5 flex items-center justify-center mx-auto mb-3">
                  <MessageSquare className="w-6 h-6 text-gray-500" />
                </div>
                <p className="text-gray-400 text-sm">No conversations yet</p>
                <p className="text-gray-500 text-xs mt-1">Start a new chat to explore your documents</p>
              </div>
            ) : (
              <div className="space-y-1">
                {recentConversations.map((conv) => (
                  <RecentItem
                    key={conv.id}
                    type="conversation"
                    title={conv.title}
                    timestamp={conv.updated_at}
                    onClick={() => navigate(`/chat/${conv.id}`)}
                  />
                ))}
              </div>
            )}
          </motion.div>
        </div>

        {/* Feature highlight */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="mt-8 glass-card p-8"
        >
          <div className="flex items-start gap-6">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500/20 to-purple-500/20 flex items-center justify-center flex-shrink-0">
              <Sparkles className="w-8 h-8 text-blue-400" />
            </div>
            
            <div className="flex-1">
              <h3 className="text-xl font-semibold mb-2">Why Structured Intelligence?</h3>
              <p className="text-gray-400 mb-4 leading-relaxed">
                Unlike NotebookLM, your data never leaves your infrastructure. 
                With local LLM support via Ollama and our 5-Layer SMC security, 
                you get the power of AI without compromising on privacy.
              </p>
              
              <div className="flex flex-wrap gap-4">
                <div className="flex items-center gap-2 text-sm text-gray-400">
                  <span className="w-2 h-2 rounded-full bg-green-400"></span>
                  100% Private - Data stays local
                </div>
                <div className="flex items-center gap-2 text-sm text-gray-400">
                  <span className="w-2 h-2 rounded-full bg-blue-400"></span>
                  Local LLMs via Ollama
                </div>
                <div className="flex items-center gap-2 text-sm text-gray-400">
                  <span className="w-2 h-2 rounded-full bg-purple-400"></span>
                  5-Layer SMC Security
                </div>
                <div className="flex items-center gap-2 text-sm text-gray-400">
                  <span className="w-2 h-2 rounded-full bg-orange-400"></span>
                  Citation-backed responses
                </div>
              </div>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  )
}
