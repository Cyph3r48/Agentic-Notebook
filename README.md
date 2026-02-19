# 🧠 Structured Intelligence

**Production-grade, private NotebookLM alternative with SMC memory integration**

A containerized document analysis and AI chat platform featuring:
- 🔐 **5-Layer SMC Security** (PI Guard, Sanitizer, Resolver, Tool Whitelist, CIFS Audit)
- 🎨 **Glass Morphism Dark UI** (Blues, Purples, Claude Orange)
- 🤖 **Multi-Model Support** (Ollama local + Claude API fallback)
- 📄 **Full Document Analysis** (.md, .pdf, .docx, .txt, .html)
- 🔒 **Team Authentication** (JWT-based with role management)
- 💾 **Persistent Memory** (PostgreSQL + Qdrant vector DB)
- 📊 **Semantic Search** across all documents
- 💬 **RAG-powered Chat** with source citations

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    STRUCTURED INTELLIGENCE                   │
├──────────────────┬──────────────────────┬───────────────────┤
│   FRONTEND       │     BACKEND API      │   INFRASTRUCTURE  │
│   React + Vite   │   FastAPI + Python   │   Docker Stack    │
├──────────────────┼──────────────────────┼───────────────────┤
│ • Glass UI       │ • Document Ingestion │ • PostgreSQL      │
│ • Framer Motion  │ • Vector Embeddings  │ • Qdrant VectorDB │
│ • TanStack Query │ • LLM Integration    │ • Redis Cache     │
│ • Zustand State  │ • SMC Security (5L)  │ • TEI Embeddings  │
│ • React Router   │ • JWT Auth           │ • Nginx Proxy     │
└──────────────────┴──────────────────────┴───────────────────┘
                              │
                   ┌──────────┴──────────┐
                   │   SMC INTEGRATION   │
                   │  (Memory Container)  │
                   └─────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- **Docker** & **Docker Compose** (v2.0+)
- **Ollama** running locally (for local LLM inference)
  ```bash
  # Install Ollama
  curl -fsSL https://ollama.com/install.sh | sh
  
  # Pull a model (choose based on your hardware)
  ollama pull llama3.2:3b-instruct-q4_K_M  # Laptop-friendly
  ollama pull gemma2:9b                     # Balanced
  ollama pull qwen2.5:14b                   # High quality
  ```

- **8GB RAM minimum** (16GB+ recommended)
- **10GB disk space** for containers and vectors

---

### 1️⃣ Clone & Setup

```bash
# Clone the repository
git clone <your-repo-url>
cd structured-intelligence

# Copy environment template
cp .env.template .env

# Edit .env with your settings
nano .env  # or vim, code, etc.
```

**Critical .env settings to change:**

```bash
# Security (CHANGE THESE!)
PGPASSWORD=your_secure_postgres_password
REDIS_PASSWORD=your_secure_redis_password
JWT_SECRET=generate_a_32_char_minimum_secret_here

# Admin user (CHANGE ON FIRST LOGIN!)
ADMIN_EMAIL=your@email.com
ADMIN_PASSWORD=temporary_secure_password

# Ollama configuration
OLLAMA_URL=http://host.docker.internal:11434
DEFAULT_MODEL=llama3.2:3b-instruct-q4_K_M

# Optional: Claude API (for premium responses)
CLAUDE_API_KEY=your_anthropic_api_key

# SMC Integration (if using existing SMC container)
SMC_ENABLED=true
SMC_ADMIN_TOKEN=your_smc_admin_token
```

---

### 2️⃣ Build & Launch

```bash
# Build all containers
docker compose build

# Start the stack
docker compose up -d

# Watch logs
docker compose logs -f
```

**Services will start on:**
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/api/docs
- Qdrant UI: http://localhost:6333/dashboard

---

### 3️⃣ First Login

1. Navigate to http://localhost:3000
2. Login with credentials from .env:
   - Email: `ADMIN_EMAIL`
   - Password: `ADMIN_PASSWORD`
3. **Immediately change your password** in Settings

---

## 📚 Usage Guide

### Uploading Documents

1. **Go to Documents** page
2. **Drag & drop** or click to upload:
   - Markdown (.md)
   - PDF (.pdf)
   - Word (.docx)
   - Text (.txt)
   - HTML (.html)
3. Documents are **automatically processed**:
   - Text extraction
   - Chunking (1000 tokens, 200 overlap)
   - Vector embedding (BAAI/bge-large-en-v1.5)
   - Stored in Qdrant + PostgreSQL

### Chatting with Documents

1. **Go to Chat** page
2. **Select model**:
   - Ollama models (local, private)
   - Claude (premium, requires API key)
3. **Ask questions** about your documents
4. **Citations** are automatically provided
5. **Source documents** are highlighted

### Document Analysis Features

- **Semantic Search**: Find similar concepts across all docs
- **Summarization**: Generate summaries of entire corpus
- **Q&A with Citations**: Ask questions, get sourced answers
- **Relationship Mapping**: Discover connections between documents

---

## 🔐 SMC Security Layers

Every request passes through 5 security layers:

### Layer 1: PI Guard
- Detects adversarial patterns (prompt injection)
- Blocks malicious instructions
- Logs attempts to audit trail

### Layer 2: Sanitizer
- Removes HTML scripts & event handlers
- Redacts PII (SSN, credit cards)
- Cleans dangerous content

### Layer 3: Resolver (Integrity)
- SHA-256 hash verification
- Detects data tampering
- Canonical store validation

### Layer 4: Tool Whitelist
- Role-based access control
- Admin token for privileged ops
- Prevents unauthorized tool use

### Layer 5: CIFS Audit
- **Every interaction logged**
- Request ID tracking
- Security event flagging
- Forensic trail for compliance

---

## 🔧 Configuration

### LLM Models

**For Laptop (8-16GB RAM):**
```bash
DEFAULT_MODEL=llama3.2:3b-instruct-q4_K_M
```

**For Desktop/Server (32GB+ RAM, GPU):**
```bash
DEFAULT_MODEL=qwen2.5:14b
# or
DEFAULT_MODEL=llama3.1:70b  # Requires 48GB+ VRAM
```

**Enable Claude Fallback:**
```bash
CLAUDE_API_KEY=sk-ant-api03-...
CLAUDE_MODEL=claude-sonnet-4-20250514
```

### Document Processing

```bash
MAX_UPLOAD_SIZE_MB=100          # Max file size
CHUNK_SIZE=1000                 # Token chunk size
CHUNK_OVERLAP=200               # Overlap for context
ALLOWED_EXTENSIONS=.md,.pdf,.docx,.txt,.html
```

### Vector Database

```bash
EMBEDDING_DIM=1024              # bge-large dimension
QDRANT_COLLECTION=si_documents  # Collection name
```

---

## 🎨 UI Customization

### Color Scheme

Located in `frontend/tailwind.config.js`:

```js
colors: {
  'dark-base': '#0a0e1a',        // Background
  'blue-500': '#0066ff',          // Primary blue
  'purple-500': '#9966ff',        // Purple accent
  'claude-orange-500': '#ff9933', // Orange accent
}
```

### Logo

Replace `frontend/public/logo.svg` with your custom logo.

Default text: **"Structured Intelligence"**

---

## 📦 Deployment

### Development (Local)

```bash
docker compose up -d
```

### Production (VPS/Server)

```bash
# Use production profile (includes Nginx SSL)
docker compose --profile production up -d

# SSL certificates go in:
nginx/ssl/cert.pem
nginx/ssl/key.pem
```

### GPU Server Setup

For better performance with larger models:

```bash
# Install NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update && sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker

# Pull GPU-optimized model
ollama pull llama3.1:70b
```

---

## 🔄 Integration with Existing SMC

If you have an existing SMC (Structured Memory Core) container:

### 1. Network Integration

```yaml
# In docker-compose.yml, add to networks:
networks:
  si_net:
    external: true
    name: kaiyi_net  # Your SMC network name
```

### 2. Enable SMC Features

```bash
# In .env
SMC_ENABLED=true
SMC_ADMIN_TOKEN=your_existing_smc_admin_token
SMC_POSTGRES_URL=postgresql://user:pass@smc-postgres:5432/kaiyi
```

### 3. Shared Memory Access

The app will use your existing SMC's:
- PostgreSQL (episodic/semantic memory)
- Qdrant (vector store)
- Audit logs (CIFS)
- Security layers (5L architecture)

---

## 📊 Monitoring

### Health Checks

```bash
# Backend health
curl http://localhost:8000/health

# Qdrant health
curl http://localhost:6333/healthz

# PostgreSQL health
docker exec -it si-postgres pg_isready
```

### Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend
docker compose logs -f frontend

# Application logs
tail -f logs/si.log
```

### Metrics

Access Prometheus metrics at:
```
http://localhost:8000/metrics
```

---

## 🛠️ Development

### Backend (FastAPI)

```bash
# Enter backend container
docker exec -it si-backend bash

# Run tests
pytest

# Format code
black app/
ruff check app/
```

### Frontend (React)

```bash
# Enter frontend container
docker exec -it si-frontend sh

# Install new package
npm install <package-name>

# Build for production
npm run build
```

---

## 🐛 Troubleshooting

### Ollama Connection Issues

```bash
# Check Ollama is running
ollama list

# Test connection from container
docker exec -it si-backend curl http://host.docker.internal:11434/api/tags
```

### Database Connection Errors

```bash
# Check PostgreSQL logs
docker compose logs postgres

# Verify credentials
docker exec -it si-postgres psql -U si_user -d structured_intelligence
```

### Vector Search Not Working

```bash
# Check Qdrant collection
curl http://localhost:6333/collections

# Verify embeddings
curl http://localhost:8080/health  # TEI service
```

---

## 🔮 Roadmap

### Phase 1 (Current)
- ✅ Document upload & processing
- ✅ Vector indexing with semantic search
- ✅ Chat interface with RAG
- ✅ Source citation & preview
- ✅ Glass morphism UI
- ✅ Docker containerized deployment

### Phase 2 (Next)
- 🔄 Audio/podcast generation (NotebookLM feature)
- 🔄 Multi-doc comparison
- 🔄 Conversation history search
- 🔄 Advanced filters (date, type, topic)
- 🔄 Export chat sessions

### Phase 3 (Future)
- 🔮 Video summaries
- 🔮 Code snippet extraction
- 🔮 Relationship graphs
- 🔮 Collaborative team features
- 🔮 Mobile apps

---

## 📄 License

[Your License Here]

---

## 🤝 Contributing

Contributions welcome! Please read CONTRIBUTING.md first.

---

## 💬 Support

- **Issues**: GitHub Issues
- **Docs**: `/docs` folder
- **Email**: [your-email]

---

## 🙏 Credits

Built with:
- FastAPI
- React
- Qdrant
- Ollama
- PostgreSQL
- SMC (Structured Memory Core)

---

**Built by Cyph3r** 🚀

---

## Backend Chat API Updates

Current backend model/provider behavior:

- `POST /api/v1/chat/conversations` accepts an optional `model`
- Anthropic models are validated against:
  - `CLAUDE_SONNET_MODEL`
  - `CLAUDE_OPUS_MODEL`
- Local Ollama model selection is controlled by `DEFAULT_MODEL` and available Ollama tags

Provider and model introspection endpoints:

- `GET /api/v1/chat/models`
- `GET /api/v1/chat/providers/health`

Streaming endpoint behavior:

- `POST /api/v1/chat/conversations/{conversation_id}/messages/stream`
- Emits SSE events: `delta`, `message`, `done`
- Persists both user and assistant messages (including token metadata)

Recommended `.env` keys:

```bash
OLLAMA_URL=http://host.docker.internal:11434
DEFAULT_MODEL=llama3.2:3b-instruct-q4_K_M

CLAUDE_API_KEY=your_anthropic_api_key
CLAUDE_SONNET_MODEL=claude-sonnet-4.6
CLAUDE_OPUS_MODEL=claude-opus-4.6
```
