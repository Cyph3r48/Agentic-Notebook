# 🧠 Structured Intelligence - Complete Project Overview

## 📁 Project Structure

```
structured-intelligence/
├── 📋 README.md                          # Main documentation
├── 🚀 quick-start.sh                     # Automated deployment script
├── 🐳 docker-compose.yml                 # Container orchestration
├── 🔐 .env.template                      # Environment configuration template
│
├── backend/                              # FastAPI Backend
│   ├── 🐳 Dockerfile                     # Backend container image
│   ├── 📦 requirements.txt               # Python dependencies
│   ├── 🗄️  init-db.sql                   # PostgreSQL schema (SMC-compatible)
│   │
│   └── app/
│       ├── main.py                       # FastAPI application entry
│       │
│       ├── core/                         # Core functionality
│       │   ├── config.py                 # Pydantic settings (SMC integration)
│       │   ├── database.py               # SQLAlchemy async DB
│       │   ├── redis_client.py           # Redis session management
│       │   └── init_db.py                # DB initialization & admin user
│       │
│       ├── models/                       # SQLAlchemy ORM models
│       │   ├── user.py                   # User model
│       │   ├── document.py               # Document model
│       │   ├── conversation.py           # Chat conversation model
│       │   ├── message.py                # Chat message model
│       │   ├── smc.py                    # SMC canonical store model
│       │   └── audit.py                  # Audit log model (CIFS Layer 5)
│       │
│       ├── services/                     # Business logic
│       │   ├── smc_service.py            # 5-Layer SMC security implementation
│       │   ├── auth_service.py           # JWT authentication
│       │   ├── document_service.py       # Document processing & chunking
│       │   ├── vector_service.py         # Qdrant vector operations
│       │   ├── llm_service.py            # Ollama + Claude integration
│       │   ├── embedding_service.py      # TEI embedding generation
│       │   └── rag_service.py            # RAG pipeline with citations
│       │
│       ├── api/                          # API endpoints
│       │   └── v1/
│       │       ├── __init__.py           # API router
│       │       ├── auth.py               # Login, register, refresh
│       │       ├── documents.py          # Upload, list, delete docs
│       │       ├── chat.py               # Chat with RAG
│       │       ├── search.py             # Semantic search
│       │       ├── analytics.py          # Usage analytics
│       │       └── admin.py              # Admin operations
│       │
│       ├── middleware/                   # Custom middleware
│       │   ├── rate_limit.py             # Rate limiting (per user)
│       │   ├── security.py               # Security headers
│       │   └── logging.py                # Request logging
│       │
│       └── utils/                        # Utilities
│           ├── pdf_parser.py             # PDF extraction
│           ├── docx_parser.py            # Word document parsing
│           ├── markdown_parser.py        # Markdown processing
│           ├── text_splitter.py          # Document chunking
│           └── validators.py             # Input validation
│
├── frontend/                             # React Frontend
│   ├── 🐳 Dockerfile                     # Frontend container image
│   ├── 📦 package.json                   # Node dependencies
│   ├── ⚙️  vite.config.js                # Vite bundler config
│   ├── 🎨 tailwind.config.js             # Tailwind CSS (glass morphism theme)
│   ├── 🌐 nginx.conf                     # Nginx production config
│   │
│   ├── public/
│   │   ├── logo.svg                      # "Structured Intelligence" logo
│   │   └── favicon.ico                   # App icon
│   │
│   └── src/
│       ├── App.jsx                       # Main app component
│       ├── main.jsx                      # React entry point
│       ├── index.css                     # Global styles
│       │
│       ├── components/                   # Reusable components
│       │   ├── Layout.jsx                # Main layout with glass nav
│       │   ├── Sidebar.jsx               # Glass morphism sidebar
│       │   ├── Header.jsx                # Top bar with user menu
│       │   ├── GlassCard.jsx             # Reusable glass card
│       │   ├── Logo.jsx                  # Animated logo component
│       │   ├── FileUpload.jsx            # Drag & drop upload
│       │   ├── DocumentCard.jsx          # Document list item
│       │   ├── ChatMessage.jsx           # Message bubble with citations
│       │   ├── ChatInput.jsx             # Chat input with model selector
│       │   ├── MarkdownRenderer.jsx      # Markdown with syntax highlighting
│       │   └── LoadingSpinner.jsx        # Animated loading state
│       │
│       ├── pages/                        # Route pages
│       │   ├── Login.jsx                 # Authentication page
│       │   ├── Dashboard.jsx             # Overview & stats
│       │   ├── Documents.jsx             # Document management
│       │   ├── Chat.jsx                  # Chat interface with RAG
│       │   ├── Analytics.jsx             # Usage analytics
│       │   └── Settings.jsx              # User settings & preferences
│       │
│       ├── store/                        # Zustand state management
│       │   ├── authStore.js              # Auth state (user, token)
│       │   ├── documentStore.js          # Documents state
│       │   ├── chatStore.js              # Conversations state
│       │   └── settingsStore.js          # App settings
│       │
│       ├── hooks/                        # Custom React hooks
│       │   ├── useAuth.js                # Authentication hook
│       │   ├── useDocuments.js           # Document operations
│       │   ├── useChat.js                # Chat with streaming
│       │   └── useDebounce.js            # Debounce utility
│       │
│       ├── api/                          # API client
│       │   ├── client.js                 # Axios instance with interceptors
│       │   ├── auth.js                   # Auth API calls
│       │   ├── documents.js              # Document API calls
│       │   ├── chat.js                   # Chat API calls
│       │   └── search.js                 # Search API calls
│       │
│       └── utils/                        # Frontend utilities
│           ├── formatters.js             # Date, number formatting
│           ├── validators.js             # Form validation
│           └── constants.js              # App constants
│
├── nginx/                                # Nginx configuration
│   ├── nginx.conf                        # Production proxy config
│   └── ssl/                              # SSL certificates (production)
│       ├── cert.pem
│       └── key.pem
│
├── docs/                                 # Additional documentation
│   ├── API.md                            # API documentation
│   ├── ARCHITECTURE.md                   # System architecture
│   ├── SMC_INTEGRATION.md                # SMC integration guide
│   └── DEPLOYMENT.md                     # Deployment guide
│
└── logs/                                 # Application logs
    └── si.log                            # Main log file
```

---

## 🎨 UI/UX Features

### Glass Morphism Design System

**Color Palette:**
- **Base**: Deep navy (#0a0e1a)
- **Primary Blue**: #0066ff (actions, links)
- **Purple Accent**: #9966ff (highlights)
- **Claude Orange**: #ff9933 (CTAs, important elements)
- **Light Blue**: #00afff (hover states)

**Glass Effects:**
- Frosted glass cards with `backdrop-filter: blur(20px)`
- Semi-transparent backgrounds `rgba(255, 255, 255, 0.05)`
- Subtle glow shadows `0 0 20px rgba(0, 102, 255, 0.4)`
- Smooth border highlights `1px solid rgba(255, 255, 255, 0.1)`

**Animations:**
- Page transitions with Framer Motion
- Staggered list reveals
- Floating background gradients
- Smooth hover states
- Loading shimmer effects

**Typography:**
- **Display**: Space Grotesk (modern, geometric)
- **Body**: Inter (readable, professional)
- **Code**: JetBrains Mono (monospace)

---

## 🔐 Security Implementation

### 5-Layer SMC Architecture

#### Layer 1: PI Guard (Adversarial Detection)
```python
# Detects and blocks:
- Prompt injection attempts
- System prompt extraction
- Jailbreak patterns
- Role hijacking
- Instruction overrides
```

#### Layer 2: Sanitizer (Content Cleaning)
```python
# Removes:
- HTML script tags
- Event handlers (onclick, etc.)
- Inline JavaScript
- Dangerous iframes/embeds
- PII patterns (SSN, credit cards)
```

#### Layer 3: Resolver (Integrity Verification)
```python
# Verifies:
- SHA-256 content hashing
- Canonical store validation
- Tamper detection
- Version tracking
- Rollback capability
```

#### Layer 4: Tool Whitelist (Access Control)
```python
# Enforces:
- Role-based permissions (admin, user, viewer)
- Admin token verification
- Read/write separation
- Tool registration
- Execution control
```

#### Layer 5: CIFS Audit (Comprehensive Logging)
```python
# Logs:
- Every request with unique ID
- User actions and resource access
- Security violations and flags
- Error details and stack traces
- IP addresses and user agents
```

---

## 🤖 LLM Integration

### Supported Models

**Ollama (Local, Private):**
- **Laptop**: llama3.2:3b-instruct-q4_K_M (4GB RAM)
- **Desktop**: gemma2:9b, qwen2.5:14b (16-32GB RAM)
- **GPU Server**: llama3.1:70b, qwen2.5:72b (48GB+ VRAM)

**Claude API (Optional, Premium):**
- claude-sonnet-4-20250514 (best quality)
- claude-haiku-4-20250514 (fast, cost-effective)

### RAG Pipeline

```
User Query
    ↓
[PI Guard Check]  ← Layer 1
    ↓
[Sanitize Input]  ← Layer 2
    ↓
[Generate Embedding] (TEI: BAAI/bge-large-en-v1.5)
    ↓
[Vector Search] (Qdrant: top 5 chunks)
    ↓
[Verify Integrity]  ← Layer 3 (SHA-256 hash check)
    ↓
[Build Context] (system prompt + retrieved docs + user query)
    ↓
[LLM Generation] (Ollama or Claude)
    ↓
[Extract Citations] (map sources back to original docs)
    ↓
[Audit Log]  ← Layer 5
    ↓
Response with Sources
```

---

## 📊 Database Schema

### Core Tables

**users**: Authentication and roles
**documents**: Uploaded files with metadata
**document_chunks**: Vectorized text segments
**conversations**: Chat sessions
**messages**: Chat history with context
**canonical_store**: SMC Table 2 (integrity verification)
**audit_log**: CIFS Layer 5 (comprehensive logging)
**sessions**: JWT session management

### Indexes

- B-tree indexes on foreign keys, timestamps
- GIN indexes on JSONB metadata
- Hash indexes on content SHA-256
- Vector indexes in Qdrant (HNSW)

---

## 🚀 Deployment Options

### 1. Local Development
```bash
./quick-start.sh
# Choose option 1
```

### 2. VPS/Server (Docker Compose)
```bash
./quick-start.sh
# Choose option 2 (production)
# Configure Nginx SSL
```

### 3. Kubernetes (Scalable)
```bash
# Convert docker-compose to k8s manifests
# Use managed PostgreSQL (RDS, Cloud SQL)
# Use managed Qdrant or Pgvector
# Deploy with kubectl apply
```

### 4. Integration with Existing SMC
```yaml
# Share network with existing SMC
networks:
  si_net:
    external: true
    name: kaiyi_net
```

---

## 🎯 Use Cases

### 1. Personal Knowledge Base
- Upload 500+ conversations
- Semantic search across all content
- Chat interface for Q&A
- Private, local AI inference

### 2. Team Documentation
- Centralized doc repository
- Role-based access control
- Collaborative search
- Audit trail for compliance

### 3. Research & Analysis
- Multi-document comparison
- Citation-backed answers
- Relationship mapping
- Export capabilities

### 4. Customer Support
- Knowledge base integration
- Quick answer retrieval
- Context-aware responses
- Performance analytics

---

## 📈 Performance Metrics

### Expected Performance (Local, 16GB RAM)

- **Document Upload**: 10-50MB/sec
- **Embedding Generation**: 50-100 chunks/sec
- **Vector Search**: <100ms (top 5 results)
- **LLM Response**: 20-50 tokens/sec (llama3.2:3b)
- **Concurrent Users**: 5-10

### GPU Server (48GB VRAM, llama3.1:70b)

- **LLM Response**: 30-80 tokens/sec
- **Concurrent Users**: 20-50

---

## 🛡️ Security Best Practices

1. **Change default passwords immediately**
2. **Use strong JWT secrets** (32+ chars, random)
3. **Enable HTTPS in production** (Nginx SSL)
4. **Rotate admin tokens regularly**
5. **Monitor audit logs** for suspicious activity
6. **Limit upload sizes** to prevent DoS
7. **Rate limit API requests** (60/min default)
8. **Keep dependencies updated** (Dependabot)
9. **Backup PostgreSQL daily** (pg_dump)
10. **Test disaster recovery** procedures

---

## 🔄 Future Roadmap

### Phase 2 (Q1 2025)
- [ ] Audio/podcast generation (TTS multi-voice)
- [ ] Video summary generation
- [ ] Advanced document comparison
- [ ] Conversation history search
- [ ] Export chat to PDF/MD

### Phase 3 (Q2 2025)
- [ ] Mobile apps (iOS, Android)
- [ ] Browser extension
- [ ] Slack/Discord integration
- [ ] Real-time collaboration
- [ ] Custom model fine-tuning

### Phase 4 (Q3 2025)
- [ ] Enterprise SSO (SAML, OAuth)
- [ ] Multi-tenancy support
- [ ] Advanced analytics dashboard
- [ ] GraphQL API
- [ ] Marketplace for plugins

---

## 📞 Support & Resources

**Documentation**: `/docs` folder
**API Reference**: http://localhost:8000/api/docs
**GitHub Issues**: [Create an issue]
**Discord Community**: [Join server]
**Email Support**: support@structured-intelligence.io

---

**Built with ❤️ by Cyph3r**
**Powered by SMC (Structured Memory Core)**
