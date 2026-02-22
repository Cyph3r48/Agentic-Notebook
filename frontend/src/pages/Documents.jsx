import { useState, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  Upload, 
  FileText, 
  Trash2, 
  RefreshCw, 
  CheckCircle, 
  AlertCircle, 
  Loader2,
  File,
  Clock,
  MoreVertical,
  Search,
} from 'lucide-react'
import { useDocuments } from '../hooks/useDocuments'
import { formatDistanceToNow } from '../lib/utils'

// Document status badge component
const StatusBadge = ({ status }) => {
  const configs = {
    pending: { icon: Clock, color: 'text-yellow-400', bg: 'bg-yellow-400/10', border: 'border-yellow-400/20', label: 'Processing' },
    completed: { icon: CheckCircle, color: 'text-green-400', bg: 'bg-green-400/10', border: 'border-green-400/20', label: 'Ready' },
    failed: { icon: AlertCircle, color: 'text-red-400', bg: 'bg-red-400/10', border: 'border-red-400/20', label: 'Failed' },
  }

  const config = configs[status] || configs.pending
  const Icon = config.icon

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${config.bg} ${config.color} border ${config.border}`}>
      <Icon className="w-3.5 h-3.5" />
      {config.label}
    </span>
  )
}

// File type icon based on extension
const FileTypeIcon = ({ fileType, className = "w-10 h-10" }) => {
  const colors = {
    pdf: 'text-red-400',
    docx: 'text-blue-400',
    doc: 'text-blue-400',
    txt: 'text-gray-400',
    md: 'text-purple-400',
    html: 'text-orange-400',
  }

  return (
    <div className={`${colors[fileType] || 'text-gray-400'} ${className}`}>
      <File className="w-full h-full" />
    </div>
  )
}

// Document card component
const DocumentCard = ({ document, onDelete, onRetry, isDeleting, isRetrying }) => {
  const [showMenu, setShowMenu] = useState(false)
  const menuRef = useRef(null)

  const handleDelete = () => {
    if (window.confirm(`Are you sure you want to delete "${document.original_filename}"? This action cannot be undone.`)) {
      onDelete(document.id)
    }
    setShowMenu(false)
  }

  const handleRetry = () => {
    onRetry(document.id)
    setShowMenu(false)
  }

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95 }}
      className="glass-card p-5 relative group"
    >
      <div className="flex items-start gap-4">
        <FileTypeIcon fileType={document.file_type} />
        
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1 min-w-0">
              <h3 className="font-medium text-white truncate" title={document.original_filename}>
                {document.original_filename}
              </h3>
              <p className="text-sm text-gray-400 mt-0.5">
                {document.file_size ? `${(document.file_size / 1024 / 1024).toFixed(2)} MB` : 'Size unknown'}
                {' • '}
                {formatDistanceToNow(document.created_at)} ago
              </p>
            </div>
            
            <div className="relative" ref={menuRef}>
              <button
                onClick={() => setShowMenu(!showMenu)}
                className="p-2 rounded-lg hover:bg-white/5 transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100"
              >
                <MoreVertical className="w-4 h-4 text-gray-400" />
              </button>
              
              <AnimatePresence>
                {showMenu && (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.95, y: -10 }}
                    animate={{ opacity: 1, scale: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95, y: -10 }}
                    className="absolute right-0 top-full mt-1 w-40 bg-surface-card border border-white/10 rounded-lg shadow-xl z-20 overflow-hidden"
                  >
                    {document.status === 'failed' && (
                      <button
                        onClick={handleRetry}
                        disabled={isRetrying}
                        className="w-full px-4 py-2.5 text-sm text-left hover:bg-white/5 flex items-center gap-2 transition-colors"
                      >
                        <RefreshCw className={`w-4 h-4 ${isRetrying ? 'animate-spin' : ''}`} />
                        Retry Processing
                      </button>
                    )}
                    <button
                      onClick={handleDelete}
                      disabled={isDeleting}
                      className="w-full px-4 py-2.5 text-sm text-left text-red-400 hover:bg-red-500/10 flex items-center gap-2 transition-colors"
                    >
                      {isDeleting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                      Delete
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>

          <div className="flex items-center gap-4 mt-3">
            <StatusBadge status={document.status} />
            {document.chunk_count > 0 && (
              <span className="text-sm text-gray-400">
                {document.chunk_count} chunk{document.chunk_count !== 1 ? 's' : ''}
              </span>
            )}
          </div>

          {document.processing_error && (
            <div className="mt-3 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
              <AlertCircle className="w-4 h-4 inline mr-2" />
              {document.processing_error}
            </div>
          )}
        </div>
      </div>
    </motion.div>
  )
}

// Upload progress component
const UploadProgress = ({ file, progress, status }) => {
  const isComplete = status === 'completed'
  const isError = status === 'error'

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: 100 }}
      className="glass-card p-4 mb-3"
    >
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-white/5 flex items-center justify-center">
          {isComplete ? (
            <CheckCircle className="w-5 h-5 text-green-400" />
          ) : isError ? (
            <AlertCircle className="w-5 h-5 text-red-400" />
          ) : (
            <Loader2 className="w-5 h-5 text-blue-400 animate-spin" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-medium text-sm text-white truncate">{file.name}</p>
          <div className="mt-1.5 h-1.5 bg-white/10 rounded-full overflow-hidden">
            <motion.div
              className={`h-full rounded-full ${isError ? 'bg-red-500' : 'bg-blue-500'}`}
              initial={{ width: 0 }}
              animate={{ width: `${isComplete ? 100 : progress}%` }}
              transition={{ duration: 0.3 }}
            />
          </div>
        </div>
        <span className="text-sm text-gray-400">{isComplete ? 'Done' : `${progress}%`}</span>
      </div>
    </motion.div>
  )
}

// Main Documents page component
export const Documents = () => {
  const [isDragging, setIsDragging] = useState(false)
  const [uploads, setUploads] = useState([])
  const [searchQuery, setSearchQuery] = useState('')
  const fileInputRef = useRef(null)

  const {
    documents,
    isLoading,
    isError,
    uploadDocument,
    deleteDocument,
    isDeleting,
    retryProcessing,
    isRetrying,
  } = useDocuments()

  // Filter documents by search
  const filteredDocuments = documents.filter(doc =>
    doc.original_filename?.toLowerCase().includes(searchQuery.toLowerCase())
  )

  // Handle file drop
  const handleDrop = async (e) => {
    e.preventDefault()
    setIsDragging(false)

    const files = Array.from(e.dataTransfer.files)
    await handleFiles(files)
  }

  // Handle file selection
  const handleFileSelect = async (e) => {
    const files = Array.from(e.target.files)
    await handleFiles(files)
  }

  // Process files for upload
  const handleFiles = async (files) => {
    for (const file of files) {
      const uploadId = `${file.name}-${Date.now()}`
      
      setUploads(prev => [...prev, {
        id: uploadId,
        file,
        progress: 0,
        status: 'uploading'
      }])

      try {
        await uploadDocument({
          file,
          onProgress: (progress) => {
            setUploads(prev =>
              prev.map(u => u.id === uploadId ? { ...u, progress } : u)
            )
          }
        })

        setUploads(prev =>
          prev.map(u => u.id === uploadId ? { ...u, status: 'completed', progress: 100 } : u)
        )
      } catch {
        setUploads(prev =>
          prev.map(u => u.id === uploadId ? { ...u, status: 'error' } : u)
        )
      }

      // Remove completed/error uploads after delay
      setTimeout(() => {
        setUploads(prev => prev.filter(u => u.id !== uploadId))
      }, 3000)
    }
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = () => {
    setIsDragging(false)
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
          <h1 className="text-4xl font-display font-bold text-gradient">
            Documents
          </h1>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="glass-button-primary px-6 py-3 flex items-center gap-2"
          >
            <Upload className="w-5 h-5" />
            Upload Document
          </button>
        </div>

        {/* Search bar */}
        {documents.length > 0 && (
          <div className="mb-6">
            <div className="relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
              <input
                type="text"
                placeholder="Search documents..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="glass-input w-full pl-12 pr-4"
              />
            </div>
          </div>
        )}

        {/* Upload progress */}
        <AnimatePresence>
          {uploads.length > 0 && (
            <div className="mb-6">
              {uploads.map(upload => (
                <UploadProgress
                  key={upload.id}
                  file={upload.file}
                  progress={upload.progress}
                  status={upload.status}
                />
              ))}
            </div>
          )}
        </AnimatePresence>

        {/* Drop zone */}
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => fileInputRef.current?.click()}
          className={`
            glass-card p-12 text-center cursor-pointer transition-all duration-300 mb-8
            ${isDragging ? 'border-blue-500 bg-blue-500/5' : ''}
            ${documents.length === 0 ? '' : 'hidden'}
          `}
        >
          <div className="w-20 h-20 rounded-2xl bg-white/5 flex items-center justify-center mx-auto mb-4">
            <Upload className={`w-10 h-10 text-blue-400 transition-transform duration-300 ${isDragging ? 'scale-110' : ''}`} />
          </div>
          <h3 className="text-xl font-semibold text-white mb-2">
            {isDragging ? 'Drop files here' : 'Drag and drop documents here'}
          </h3>
          <p className="text-gray-400 mb-4">
            or click to browse from your computer
          </p>
          <div className="flex items-center justify-center gap-4 text-sm text-gray-500">
            <span className="flex items-center gap-1"><FileText className="w-4 h-4" /> PDF</span>
            <span className="flex items-center gap-1"><FileText className="w-4 h-4" /> DOCX</span>
            <span className="flex items-center gap-1"><FileText className="w-4 h-4" /> TXT</span>
            <span className="flex items-center gap-1"><FileText className="w-4 h-4" /> MD</span>
          </div>
        </div>

        {/* Documents grid */}
        {isLoading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-8 h-8 text-blue-400 animate-spin" />
          </div>
        ) : isError ? (
          <div className="glass-card p-8 text-center">
            <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-4" />
            <h3 className="text-xl font-semibold text-white mb-2">Failed to load documents</h3>
            <p className="text-gray-400">Please try again later</p>
          </div>
        ) : filteredDocuments.length === 0 ? (
          searchQuery ? (
            <div className="glass-card p-8 text-center">
              <Search className="w-12 h-12 text-gray-400 mx-auto mb-4" />
              <h3 className="text-xl font-semibold text-white mb-2">No documents found</h3>
              <p className="text-gray-400">Try adjusting your search query</p>
            </div>
          ) : documents.length === 0 ? null : (
            <div className="glass-card p-8 text-center">
              <FileText className="w-12 h-12 text-gray-400 mx-auto mb-4" />
              <h3 className="text-xl font-semibold text-white mb-2">No documents yet</h3>
              <p className="text-gray-400">Upload your first document to get started</p>
            </div>
          )
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <AnimatePresence mode="popLayout">
              {filteredDocuments.map((doc) => (
                <DocumentCard
                  key={doc.id}
                  document={doc}
                  onDelete={deleteDocument}
                  onRetry={retryProcessing}
                  isDeleting={isDeleting}
                  isRetrying={isRetrying}
                />
              ))}
            </AnimatePresence>
          </div>
        )}

        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.doc,.txt,.md,.html"
          onChange={handleFileSelect}
          className="hidden"
        />
      </motion.div>
    </div>
  )
}
