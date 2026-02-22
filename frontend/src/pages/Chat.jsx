import { useState, useRef, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  MessageSquare, 
  Plus, 
  Trash2, 
  MoreVertical, 
  Send, 
  Loader2, 
  BookOpen,
  Cpu,
  Check,
  ChevronDown,
  FileText,
  Edit2,
  Sparkles,
  MessageCircle,
} from 'lucide-react'
import { toast } from 'sonner'
import { useConversations } from '../hooks/useConversations'
import { useMessages, messageKeys } from '../hooks/useMessages'
import { useModels } from '../hooks/useChatModels'
import { useAuthStore } from '../store/authStore'
import { formatDistanceToNow } from '../lib/utils'
import { streamConversationMessage } from '../lib/chatApi'
import { chatAPI } from '../api/chat'

// Message component
const ChatMessage = ({ message, isLast }) => {
  const isUser = message.role === 'user'
  const hasSources = message.sources && message.sources.length > 0
  const [showSources, setShowSources] = useState(false)

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={`py-6 ${isUser ? 'bg-transparent' : 'bg-white/[0.02]'}`}
    >
      <div className="max-w-4xl mx-auto px-4">
        <div className="flex gap-4">
          {/* Avatar */}
          <div className={`
            w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0
            ${isUser ? 'bg-blue-500/20' : 'bg-purple-500/20'}
          `}>
            {isUser ? (
              <MessageCircle className="w-4 h-4 text-blue-400" />
            ) : (
              <Sparkles className="w-4 h-4 text-purple-400" />
            )}
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <span className="font-medium text-sm">
                {isUser ? 'You' : 'Assistant'}
              </span>
              {message.model && !isUser && (
                <span className="text-xs text-gray-500">
                  using {message.model}
                </span>
              )}
            </div>

            <div className="prose prose-invert prose-sm max-w-none">
              <div className="whitespace-pre-wrap text-gray-200 leading-relaxed">
                {message.content || (isLast && !isUser ? (
                  <div className="flex items-center gap-2 text-gray-500">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Thinking...
                  </div>
                ) : null)}
              </div>
            </div>

            {/* Sources */}
            {hasSources && (
              <div className="mt-4">
                <button
                  onClick={() => setShowSources(!showSources)}
                  className="flex items-center gap-2 text-xs text-blue-400 hover:text-blue-300 transition-colors"
                >
                  <BookOpen className="w-3.5 h-3.5" />
                  {message.sources.length} source{message.sources.length !== 1 ? 's' : ''} cited
                  <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showSources ? 'rotate-180' : ''}`} />
                </button>

                <AnimatePresence>
                  {showSources && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      className="mt-2 space-y-2 overflow-hidden"
                    >
                      {message.sources.map((source, idx) => (
                        <div
                          key={idx}
                          className="p-3 rounded-lg bg-white/5 border border-white/10 text-sm"
                        >
                          <div className="flex items-center gap-2 mb-1">
                            <FileText className="w-4 h-4 text-blue-400" />
                            <span className="font-medium text-white">
                              {source.original_filename} #{source.chunk_index}
                            </span>
                            <span className="text-xs text-gray-500">
                              (Score: {(source.score * 100).toFixed(1)}%)
                            </span>
                          </div>
                          <p className="text-gray-400 text-xs line-clamp-2">
                            {source.snippet}
                          </p>
                        </div>
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  )
}

// Conversation sidebar item
const ConversationItem = ({ conversation, isActive, onClick, onDelete, onRename }) => {
  const [showMenu, setShowMenu] = useState(false)
  const [isRenaming, setIsRenaming] = useState(false)
  const [newTitle, setNewTitle] = useState(conversation.title || '')

  const handleRename = async () => {
    if (newTitle.trim() && newTitle !== conversation.title) {
      await onRename(conversation.id, newTitle.trim())
    }
    setIsRenaming(false)
    setShowMenu(false)
  }

  return (
    <div
      onClick={onClick}
      className={`
        group relative flex items-center gap-3 p-3 rounded-lg cursor-pointer
        transition-all duration-200
        ${isActive ? 'bg-white/10' : 'hover:bg-white/5'}
      `}
    >
      <MessageSquare className="w-4 h-4 text-gray-400 flex-shrink-0" />
      
      {isRenaming ? (
        <input
          type="text"
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
          onBlur={handleRename}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleRename()
            if (e.key === 'Escape') {
              setIsRenaming(false)
              setNewTitle(conversation.title || '')
            }
          }}
          autoFocus
          className="flex-1 bg-transparent text-sm outline-none"
          onClick={(e) => e.stopPropagation()}
        />
      ) : (
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">
            {conversation.title || 'Untitled Conversation'}
          </p>
          <p className="text-xs text-gray-500">
            {formatDistanceToNow(conversation.updated_at)} ago
          </p>
        </div>
      )}

      <div className="relative">
        <button
          onClick={(e) => {
            e.stopPropagation()
            setShowMenu(!showMenu)
          }}
          className={`
            p-1.5 rounded opacity-0 group-hover:opacity-100
            hover:bg-white/10 transition-all
            ${showMenu ? 'opacity-100' : ''}
          `}
        >
          <MoreVertical className="w-4 h-4 text-gray-400" />
        </button>

        <AnimatePresence>
          {showMenu && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="absolute right-0 top-full mt-1 w-36 bg-surface-card border border-white/10 rounded-lg shadow-xl z-50 overflow-hidden"
            >
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  setIsRenaming(true)
                  setShowMenu(false)
                }}
                className="w-full px-4 py-2 text-sm text-left hover:bg-white/5 flex items-center gap-2"
              >
                <Edit2 className="w-4 h-4" /> Rename
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  if (window.confirm('Delete this conversation?')) {
                    onDelete(conversation.id)
                  }
                  setShowMenu(false)
                }}
                className="w-full px-4 py-2 text-sm text-left text-red-400 hover:bg-red-500/10 flex items-center gap-2"
              >
                <Trash2 className="w-4 h-4" /> Delete
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}

// Model selector dropdown
const ModelSelector = ({ models, selected, onSelect, isLoading }) => {
  const [isOpen, setIsOpen] = useState(false)
  const containerRef = useRef(null)

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/5 text-sm text-gray-400">
        <Loader2 className="w-4 h-4 animate-spin" />
        Loading models...
      </div>
    )
  }

  const selectedModel = models?.ollama?.find(m => m.id === selected) || 
                       models?.anthropic?.find(m => m.id === selected) ||
                       { name: selected }

  return (
    <div ref={containerRef} className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-sm transition-colors"
      >
        <Cpu className="w-4 h-4 text-blue-400" />
        <span className="text-gray-300">{selectedModel.name || selected}</span>
        <ChevronDown className={`w-4 h-4 text-gray-500 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      <AnimatePresence>
        {isOpen && models && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="absolute bottom-full mb-2 left-0 w-64 bg-surface-card border border-white/10 rounded-lg shadow-xl overflow-hidden z-50"
          >
            {models.ollama?.length > 0 && (
              <div className="p-2">
                <p className="px-2 py-1 text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Local Models (Ollama)
                </p>
                {models.ollama.map((model) => (
                  <button
                    key={model.id}
                    onClick={() => {
                      onSelect(model.id)
                      setIsOpen(false)
                    }}
                    className={`
                      w-full px-2 py-2 rounded text-left text-sm flex items-center justify-between
                      ${selected === model.id ? 'bg-blue-500/20 text-blue-400' : 'hover:bg-white/5'}
                    `}
                  >
                    {model.name}
                    {selected === model.id && <Check className="w-4 h-4" />}
                  </button>
                ))}
              </div>
            )}

            {models.anthropic?.length > 0 && (
              <div className="p-2 border-t border-white/10">
                <p className="px-2 py-1 text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Claude API
                </p>
                {models.anthropic.map((model) => (
                  <button
                    key={model.id}
                    onClick={() => {
                      onSelect(model.id)
                      setIsOpen(false)
                    }}
                    className={`
                      w-full px-2 py-2 rounded text-left text-sm flex items-center justify-between
                      ${selected === model.id ? 'bg-orange-500/20 text-orange-400' : 'hover:bg-white/5'}
                    `}
                  >
                    {model.name}
                    {selected === model.id && <Check className="w-4 h-4" />}
                  </button>
                ))}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// Main Chat component
export const Chat = () => {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { accessToken } = useAuthStore()
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [useRag, setUseRag] = useState(true)
  const [selectedModel, setSelectedModel] = useState('llama3.2')

  // Fetch conversations and messages
  const {
    conversations,
    isLoading: isLoadingConversations,
    createConversation,
    deleteConversation,
    updateConversation,
  } = useConversations()

  const {
    messages,
    isLoading: isLoadingMessages,
    refetch: refetchMessages,
  } = useMessages(conversationId)

  const { data: modelsData, isLoading: isLoadingModels } = useModels()

  const addOptimisticMessageForConversation = (targetConversationId, message) => {
    queryClient.setQueryData(messageKeys.lists(targetConversationId), (old) => {
      if (!old) return [message]
      return [...old, message]
    })
  }

  const updateMessageForConversation = (targetConversationId, messageId, updates) => {
    queryClient.setQueryData(messageKeys.lists(targetConversationId), (old) => {
      if (!old) return []
      return old.map((msg) => (msg.id === messageId ? { ...msg, ...updates } : msg))
    })
  }

  // Set selected model from conversation when loaded
  useEffect(() => {
    if (conversationId && conversations.length > 0) {
      const conv = conversations.find(c => c.id === conversationId)
      if (conv?.model) {
        setSelectedModel(conv.model)
      }
    }
  }, [conversationId, conversations])

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Create new conversation
  const handleNewConversation = async () => {
    const newConversation = await createConversation({
      title: 'New Conversation',
      model: selectedModel,
    })
    navigate(`/chat/${newConversation.id}`)
  }

  // Send message with streaming
  const handleSend = async () => {
    if (!input.trim() || isStreaming) return

    const messageContent = input.trim()
    setInput('')

    // Create conversation if needed
    let currentConversationId = conversationId
    if (!currentConversationId) {
      const newConversation = await createConversation({
        title: messageContent.slice(0, 50) || 'New Conversation',
        model: selectedModel,
      })
      currentConversationId = newConversation.id
      navigate(`/chat/${currentConversationId}`)
    }

    setIsStreaming(true)

    try {
      let tempAssistantId = null
      let streamBuffer = ''
      addOptimisticMessageForConversation(currentConversationId, {
        id: `temp-user-${Date.now()}`,
        role: 'user',
        content: messageContent,
        created_at: new Date().toISOString(),
        sources: [],
      })
      tempAssistantId = `temp-assistant-${Date.now()}`
      addOptimisticMessageForConversation(currentConversationId, {
        id: tempAssistantId,
        role: 'assistant',
        content: '',
        created_at: new Date().toISOString(),
        sources: [],
        model: selectedModel,
      })

      for await (const event of streamConversationMessage(
        currentConversationId,
        messageContent,
        useRag,
        accessToken
      )) {
        if (event.type === 'delta' && tempAssistantId && event.data?.text) {
          streamBuffer += event.data.text
          updateMessageForConversation(currentConversationId, tempAssistantId, {
            content: streamBuffer,
          })
        }
        if (event.type === 'message') {
          if (tempAssistantId) {
            updateMessageForConversation(currentConversationId, tempAssistantId, {
              sources: event.data?.sources || [],
            })
          }
          break
        }
      }

      // Refetch to get final messages with IDs
      await refetchMessages()
    } catch (error) {
      console.error('Streaming error:', error)
      // Fall back to non-streaming
      try {
        await chatAPI.sendMessage(currentConversationId, messageContent, useRag)
      } catch (fallbackError) {
        console.error('Fallback error:', fallbackError)
        const detail = fallbackError?.response?.data?.message || fallbackError?.response?.data?.detail
        toast.error(detail || 'Unable to send message. Please try again.')
      }
    } finally {
      try {
        await queryClient.invalidateQueries({ queryKey: messageKeys.lists(currentConversationId) })
        await queryClient.invalidateQueries({ queryKey: ['conversations'] })
        if (conversationId === currentConversationId) {
          await refetchMessages()
        }
      } catch {
        // Keep UI responsive if refresh fails after stream/fallback.
      }
      setIsStreaming(false)
    }
  }

  // Handle key press
  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex h-[calc(100vh-4rem)]">
      {/* Sidebar */}
      <div className="w-72 bg-white/[0.02] border-r border-white/10 flex flex-col">
        <div className="p-4 border-b border-white/10">
          <button
            onClick={handleNewConversation}
            className="w-full glass-button-primary py-3 flex items-center justify-center gap-2"
          >
            <Plus className="w-4 h-4" />
            New Conversation
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {isLoadingConversations ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-5 h-5 text-gray-500 animate-spin" />
            </div>
          ) : conversations.length === 0 ? (
            <p className="text-center text-gray-500 text-sm py-8">
              No conversations yet
            </p>
          ) : (
            conversations.map((conv) => (
              <ConversationItem
                key={conv.id}
                conversation={conv}
                isActive={conv.id === conversationId}
                onClick={() => navigate(`/chat/${conv.id}`)}
                onDelete={deleteConversation}
                onRename={(id, title) => updateConversation({ conversationId: id, title })}
              />
            ))
          )}
        </div>
      </div>

      {/* Main chat area */}
      <div className="flex-1 flex flex-col bg-transparent">
        {conversationId ? (
          <>
            {/* Messages */}
            <div className="flex-1 overflow-y-auto">
              {isLoadingMessages ? (
                <div className="flex items-center justify-center h-full">
                  <Loader2 className="w-6 h-6 text-gray-500 animate-spin" />
                </div>
              ) : messages.length === 0 ? (
                <div className="flex items-center justify-center h-full">
                  <div className="text-center">
                    <MessageSquare className="w-12 h-12 text-gray-600 mx-auto mb-4" />
                    <p className="text-gray-400 mb-2">Start a conversation</p>
                    <p className="text-sm text-gray-500">
                      Send a message to begin chatting with AI
                    </p>
                  </div>
                </div>
              ) : (
                messages.map((message, idx) => (
                  <ChatMessage
                    key={message.id}
                    message={message}
                    isLast={idx === messages.length - 1 && message.role === 'assistant'}
                  />
                ))
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input area */}
            <div className="border-t border-white/10 p-4">
              <div className="max-w-4xl mx-auto">
                <div className="glass-card p-2">
                  <textarea
                    ref={inputRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyPress}
                    placeholder="Type your message..."
                    rows={1}
                    className="w-full bg-transparent border-0 outline-none resize-none text-gray-200 placeholder-gray-500 px-3 py-2"
                    style={{ minHeight: '44px', maxHeight: '200px' }}
                  />

                  <div className="flex items-center justify-between px-2 pt-2 border-t border-white/10">
                    <div className="flex items-center gap-3">
                      <ModelSelector
                        models={modelsData}
                        selected={selectedModel}
                        onSelect={setSelectedModel}
                        isLoading={isLoadingModels}
                      />

                      <button
                        onClick={() => setUseRag(!useRag)}
                        className={`
                          flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors
                          ${useRag ? 'bg-blue-500/20 text-blue-400' : 'bg-white/5 text-gray-400 hover:bg-white/10'}
                        `}
                      >
                        <BookOpen className="w-4 h-4" />
                        {useRag ? 'RAG On' : 'RAG Off'}
                      </button>
                    </div>

                    <button
                      onClick={handleSend}
                      disabled={!input.trim() || isStreaming}
                      className={`
                        flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm
                        ${!input.trim() || isStreaming
                          ? 'bg-white/5 text-gray-500 cursor-not-allowed'
                          : 'bg-blue-500 hover:bg-blue-600 text-white'
                        }
                        transition-colors
                      `}
                    >
                      {isStreaming ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          Sending...
                        </>
                      ) : (
                        <>
                          <Send className="w-4 h-4" />
                          Send
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                className="w-20 h-20 rounded-2xl bg-gradient-to-br from-blue-500/20 to-purple-500/20 flex items-center justify-center mx-auto mb-6"
              >
                <MessageSquare className="w-10 h-10 text-blue-400" />
              </motion.div>
              <h2 className="text-2xl font-display font-bold mb-2">Chat with Your Documents</h2>
              <p className="text-gray-400 max-w-md mb-6">
                Start a conversation to chat with AI powered by your documents. 
                Enable RAG for citations from your knowledge base.
              </p>
              <button
                onClick={handleNewConversation}
                className="glass-button-primary px-6 py-3"
              >
                Start New Conversation
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
