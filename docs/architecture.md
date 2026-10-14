# 🏗️ Structured Intelligence - System Architecture

## Complete System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         STRUCTURED INTELLIGENCE                              │
│                   Private NotebookLM Alternative + SMC                       │
└─────────────────────────────────────────────────────────────────────────────┘

                                  USERS
                                    ↓
                        ┌───────────────────────┐
                        │   Web Browser/Client  │
                        └───────────┬───────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
            ┌───────▼────────┐           ┌─────────▼──────────┐
            │   FRONTEND     │           │    NGINX (Prod)    │
            │  React + Vite  │◄──────────┤   Reverse Proxy    │
            │  Port 3000     │           │    SSL/TLS         │
            └───────┬────────┘           └─────────┬──────────┘
                    │                               │
                    │         API Calls             │
                    └───────────────┬───────────────┘
                                    │
                        ┌───────────▼──────────────┐
                        │     BACKEND API          │
                        │   FastAPI (Python)       │
                        │      Port 8000           │
                        └──────────┬───────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
┌───────▼──────────┐   ┌───────────▼──────────┐   ┌──────────▼─────────┐
│  SMC SECURITY    │   │   CORE SERVICES      │   │   INTEGRATIONS     │
│  (5 Layers)      │   │                      │   │                    │
├──────────────────┤   ├──────────────────────┤   ├────────────────────┤
│ 1. PI Guard      │   │ • Document Parser    │   │ • Ollama (Local)   │
│ 2. Sanitizer     │   │ • Text Chunker       │   │ • Claude API       │
│ 3. Resolver      │   │ • RAG Pipeline       │   │ • TEI Embeddings   │
│ 4. Tool Whitelist│   │ • Auth (JWT)         │   │                    │
│ 5. CIFS Audit    │   │ • Session Mgmt       │   │                    │
└──────────────────┘   └──────────────────────┘   └────────────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
┌───────▼──────────┐   ┌───────────▼──────────┐   ┌──────────▼─────────┐
│   POSTGRESQL     │   │      QDRANT          │   │      REDIS         │
│                  │   │   Vector Database    │   │   Cache/Session    │
│ • Users          │   │                      │   │                    │
│ • Documents      │   │ • Document Vectors   │   │ • Session Tokens   │
│ • Conversations  │   │ • Semantic Search    │   │ • Rate Limiting    │
│ • Messages       │   │ • HNSW Index         │   │ • Cache Layer      │
│ • Audit Logs     │   │ • 1024-dim vectors   │   │                    │
│ • Canonical Store│   │                      │   │                    │
│   (Table 2)      │   │                      │   │                    │
└──────────────────┘   └──────────────────────┘   └────────────────────┘
```

---

## Data Flow: Document Upload → Chat

```
1. USER UPLOADS DOCUMENT
   ↓
┌──────────────────────────────────────────────────────────────┐
│ FRONTEND                                                      │
│ • React Dropzone captures file                              │
│ • Validates file type (.md, .pdf, .docx, .txt)              │
│ • Shows upload progress                                     │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ↓ POST /api/v1/documents/upload
┌──────────────────────────────────────────────────────────────┐
│ BACKEND API - SMC Layer 1: PI GUARD                         │
│ • Scan filename for adversarial patterns                    │
│ • Check file extension whitelist                            │
│ • Verify MIME type                                          │
└────────────────────────┬─────────────────────────────────────┘
                         │ ✅ Passed
                         ↓
┌──────────────────────────────────────────────────────────────┐
│ DOCUMENT SERVICE                                             │
│ • Save file to /uploads directory                           │
│ • Compute SHA-256 hash (SMC Layer 3: Resolver)              │
│ • Extract text based on file type:                          │
│   - PDF: pypdf                                               │
│   - DOCX: python-docx                                        │
│   - MD/TXT: direct read                                     │
│ • Store metadata in PostgreSQL                              │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ↓
┌──────────────────────────────────────────────────────────────┐
│ TEXT SPLITTER                                                │
│ • Chunk text (CHUNK_SIZE=1000, OVERLAP=200)                 │
│ • Preserve sentence boundaries                              │
│ • Generate chunk metadata (page, section, etc.)             │
│ • Compute hash for each chunk (SMC Layer 3)                 │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ↓
┌──────────────────────────────────────────────────────────────┐
│ SMC Layer 2: SANITIZER                                       │
│ • Remove HTML scripts, event handlers                       │
│ • Redact PII (SSN, credit cards)                            │
│ • Clean dangerous content                                   │
└────────────────────────┬─────────────────────────────────────┘
                         │ ✅ Sanitized
                         ↓
┌──────────────────────────────────────────────────────────────┐
│ EMBEDDING SERVICE (TEI)                                      │
│ • Generate embeddings for each chunk                        │
│ • Model: BAAI/bge-large-en-v1.5 (1024-dim)                  │
│ • Batch process for efficiency                              │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ↓
┌──────────────────────────────────────────────────────────────┐
│ VECTOR DATABASE (Qdrant)                                     │
│ • Store embeddings with metadata                            │
│ • Build HNSW index for fast search                          │
│ • Link to PostgreSQL record via vector_id                   │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ↓
┌──────────────────────────────────────────────────────────────┐
│ SMC Layer 5: CIFS AUDIT                                      │
│ • Log document upload event                                 │
│ • Record: user_id, document_id, timestamp, hash             │
│ • Store in audit_log table                                  │
└──────────────────────────────────────────────────────────────┘
                         │
                         ↓ Success Response
                    FRONTEND
                  (Document listed)


2. USER ASKS QUESTION
   ↓
┌──────────────────────────────────────────────────────────────┐
│ FRONTEND                                                      │
│ • User types question in chat                               │
│ • Selects model (Ollama/Claude)                             │
│ • Clicks send                                               │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ↓ POST /api/v1/chat/conversations/{id}/messages
┌──────────────────────────────────────────────────────────────┐
│ SMC Layer 1: PI GUARD                                        │
│ • Scan for prompt injection attempts                        │
│ • Check for adversarial patterns                            │
│ • Risk scoring                                              │
└────────────────────────┬─────────────────────────────────────┘
                         │ ✅ Safe
                         ↓
┌──────────────────────────────────────────────────────────────┐
│ SMC Layer 2: SANITIZER                                       │
│ • Clean user input                                          │
│ • Remove dangerous content                                  │
└────────────────────────┬─────────────────────────────────────┘
                         │ ✅ Sanitized
                         ↓
┌──────────────────────────────────────────────────────────────┐
│ RAG SERVICE - Embedding Query                                │
│ • Generate embedding for user question                      │
│ • Same model as documents (bge-large-en-v1.5)               │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ↓
┌──────────────────────────────────────────────────────────────┐
│ QDRANT - Vector Search                                       │
│ • Search for top 5 similar chunks                           │
│ • Use cosine similarity                                     │
│ • Return: chunk content + metadata + score                  │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ↓
┌──────────────────────────────────────────────────────────────┐
│ SMC Layer 3: RESOLVER                                        │
│ • Retrieve chunks from PostgreSQL                           │
│ • Verify SHA-256 hash for each chunk                        │
│ • Ensure data integrity                                     │
└────────────────────────┬─────────────────────────────────────┘
                         │ ✅ Verified
                         ↓
┌──────────────────────────────────────────────────────────────┐
│ RAG SERVICE - Build Context                                  │
│ • System prompt                                             │
│ • Retrieved document chunks (context)                       │
│ • User question                                             │
│ • Combine into single prompt                                │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ↓
┌──────────────────────────────────────────────────────────────┐
│ SMC Layer 4: TOOL WHITELIST                                  │
│ • Check if user has permission to chat                      │
│ • Verify model access (Ollama/Claude)                       │
│ • Check rate limits                                         │
└────────────────────────┬─────────────────────────────────────┘
                         │ ✅ Authorized
                         ↓
┌──────────────────────────────────────────────────────────────┐
│ LLM GENERATION                                               │
│                                                              │
│ Option 1: OLLAMA (Local)                                    │
│ • POST to http://localhost:11434/api/generate              │
│ • Model: llama3.2:3b (or selected)                         │
│ • Stream response                                           │
│                                                              │
│ Option 2: CLAUDE (API)                                      │
│ • POST to https://api.anthropic.com/v1/messages            │
│ • Model: claude-sonnet-4                                   │
│ • Stream response                                           │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ↓
┌──────────────────────────────────────────────────────────────┐
│ CITATION EXTRACTION                                          │
│ • Parse LLM response                                        │
│ • Extract which chunks were used                            │
│ • Map back to original documents                            │
│ • Build source attribution                                  │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ↓
┌──────────────────────────────────────────────────────────────┐
│ SMC Layer 5: CIFS AUDIT                                      │
│ • Log chat interaction                                      │
│ • Record: user, question, model, tokens, sources            │
│ • Store in audit_log and messages tables                    │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ↓ Stream Response
                    FRONTEND
        (Display answer with citations)
```

---

## SMC 5-Layer Security Deep Dive

```
╔═══════════════════════════════════════════════════════════════╗
║            SMC SECURITY ARCHITECTURE (5 LAYERS)                ║
╚═══════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────┐
│ Layer 1: PI GUARD (Adversarial Pattern Detection)           │
├─────────────────────────────────────────────────────────────┤
│ INPUT: User content (query, upload, any text input)        │
│                                                             │
│ PROCESS:                                                    │
│ 1. Scan for adversarial patterns:                          │
│    • "ignore previous instructions"                        │
│    • "reveal system prompt"                                │
│    • "you are now", "pretend you are"                      │
│    • Jailbreak attempts                                    │
│ 2. Calculate risk score (0.0-1.0)                          │
│ 3. Block if risk > threshold (0.1)                         │
│                                                             │
│ OUTPUT: {passed: bool, patterns: [], risk_score: float}    │
│                                                             │
│ ON FAILURE: Log to audit, return 400 error                 │
└─────────────────────────────────────────────────────────────┘
                         ↓ PASSED
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: SANITIZER (Content Cleaning)                      │
├─────────────────────────────────────────────────────────────┤
│ INPUT: Raw content                                          │
│                                                             │
│ PROCESS:                                                    │
│ 1. Remove dangerous elements:                              │
│    • <script> tags                                         │
│    • Event handlers (onclick, onload, etc.)                │
│    • javascript: protocols                                 │
│    • Dangerous tags (iframe, embed, object)                │
│ 2. Redact PII:                                             │
│    • SSN: XXX-XX-XXXX → [SSN_REDACTED]                     │
│    • Credit cards: XXXX-XXXX-XXXX-XXXX → [CC_REDACTED]     │
│ 3. Normalize whitespace and encoding                       │
│                                                             │
│ OUTPUT: Sanitized, safe content                            │
└─────────────────────────────────────────────────────────────┘
                         ↓ SANITIZED
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: RESOLVER (Integrity Verification)                 │
├─────────────────────────────────────────────────────────────┤
│ INPUT: Content to verify                                    │
│                                                             │
│ PROCESS:                                                    │
│ 1. Compute SHA-256 hash:                                   │
│    content_hash = sha256(content.encode('utf-8'))          │
│                                                             │
│ 2. For WRITES:                                             │
│    • Store in canonical_store table                        │
│    • Immutable=true, version=1                             │
│                                                             │
│ 3. For READS:                                              │
│    • Retrieve expected_hash from canonical_store           │
│    • Compute actual_hash from retrieved content            │
│    • Compare: actual_hash == expected_hash                 │
│                                                             │
│ OUTPUT: Verified content OR integrity violation            │
│                                                             │
│ ON FAILURE: Log security event, trigger rollback           │
└─────────────────────────────────────────────────────────────┘
                         ↓ VERIFIED
┌─────────────────────────────────────────────────────────────┐
│ Layer 4: TOOL WHITELIST (Execution Control)                │
├─────────────────────────────────────────────────────────────┤
│ INPUT: (tool_name, user_role, admin_token)                 │
│                                                             │
│ TOOL REGISTRY:                                             │
│ • Read tools: query_documents, search_memory, etc.         │
│   - Allowed for: all authenticated users                   │
│                                                             │
│ • Write tools: store_document, create_conversation, etc.   │
│   - Allowed for: user, admin roles                         │
│                                                             │
│ • Admin tools: delete_document, purge_memory, export       │
│   - Required: admin role + valid SMC_ADMIN_TOKEN          │
│                                                             │
│ PROCESS:                                                    │
│ 1. Check if tool exists in whitelist                       │
│ 2. Verify user has required role                           │
│ 3. For admin tools, verify SMC_ADMIN_TOKEN                 │
│ 4. Grant or deny execution                                 │
│                                                             │
│ OUTPUT: {authorized: bool}                                 │
│                                                             │
│ ON FAILURE: Log unauthorized attempt, return 403           │
└─────────────────────────────────────────────────────────────┘
                         ↓ AUTHORIZED
┌─────────────────────────────────────────────────────────────┐
│ Layer 5: CIFS AUDIT (Comprehensive Logging)                │
├─────────────────────────────────────────────────────────────┤
│ PROCESS:                                                    │
│ 1. Generate unique request_id (UUID)                       │
│ 2. Log to audit_log table:                                 │
│    • request_id: UUID                                      │
│    • user_id: UUID                                         │
│    • action: string (e.g., "document_upload")              │
│    • resource_type: "document", "conversation", etc.       │
│    • resource_id: UUID of affected resource                │
│    • ip_address: Client IP                                 │
│    • user_agent: Client browser/app                        │
│    • request_body: JSONB (sanitized)                       │
│    • response_status: HTTP status code                     │
│    • error_message: If applicable                          │
│    • security_layer: Which layer triggered event           │
│    • flagged: Boolean (security violations)                │
│    • flag_reason: Why flagged                              │
│    • created_at: Timestamp                                 │
│                                                             │
│ 3. For security violations (Layers 1-4 failures):          │
│    • Set flagged=true                                      │
│    • Include detailed reason                               │
│    • Alert administrators (optional)                       │
│                                                             │
│ OUTPUT: request_id for tracking                            │
│                                                             │
│ RETENTION: Permanent (or per compliance policy)            │
└─────────────────────────────────────────────────────────────┘
```

---

## Tech Stack Matrix

```
┌────────────────────┬─────────────────────┬──────────────────────┐
│  Component         │  Technology         │  Purpose             │
├────────────────────┼─────────────────────┼──────────────────────┤
│ Frontend           │ React 18            │ UI framework         │
│                    │ Vite 5              │ Build tool           │
│                    │ Tailwind CSS 3      │ Styling              │
│                    │ Framer Motion       │ Animations           │
│                    │ TanStack Query      │ Data fetching        │
│                    │ Zustand             │ State management     │
│                    │ React Router        │ Routing              │
├────────────────────┼─────────────────────┼──────────────────────┤
│ Backend            │ FastAPI 0.115       │ Web framework        │
│                    │ Python 3.11         │ Language             │
│                    │ Uvicorn             │ ASGI server          │
│                    │ Pydantic            │ Data validation      │
├────────────────────┼─────────────────────┼──────────────────────┤
│ Database           │ PostgreSQL 16       │ Structured data      │
│                    │ pgvector            │ Vector extension     │
│                    │ SQLAlchemy          │ ORM                  │
│                    │ Alembic             │ Migrations           │
├────────────────────┼─────────────────────┼──────────────────────┤
│ Vector DB          │ Qdrant              │ Vector search        │
│                    │ HNSW index          │ Fast similarity      │
├────────────────────┼─────────────────────┼──────────────────────┤
│ Embeddings         │ TEI                 │ Embedding service    │
│                    │ bge-large-en-v1.5   │ Model (1024-dim)     │
├────────────────────┼─────────────────────┼──────────────────────┤
│ Cache              │ Redis 7             │ Sessions, cache      │
│                    │ Hiredis             │ High-perf client     │
├────────────────────┼─────────────────────┼──────────────────────┤
│ LLM (Local)        │ Ollama              │ Model runtime        │
│                    │ Llama 3.2           │ Primary model        │
│                    │ Gemma 2, Qwen 2.5   │ Alternative models   │
├────────────────────┼─────────────────────┼──────────────────────┤
│ LLM (Cloud)        │ Claude API          │ Premium responses    │
│                    │ Anthropic SDK       │ Client library       │
├────────────────────┼─────────────────────┼──────────────────────┤
│ Document Parsing   │ pypdf               │ PDF extraction       │
│                    │ python-docx         │ Word docs            │
│                    │ markdown            │ Markdown parsing     │
│                    │ BeautifulSoup       │ HTML parsing         │
├────────────────────┼─────────────────────┼──────────────────────┤
│ Infrastructure     │ Docker              │ Containerization     │
│                    │ Docker Compose      │ Orchestration        │
│                    │ Nginx               │ Reverse proxy        │
├────────────────────┼─────────────────────┼──────────────────────┤
│ Security           │ JWT                 │ Authentication       │
│                    │ bcrypt              │ Password hashing     │
│                    │ SHA-256             │ Content hashing      │
│                    │ SMC Architecture    │ 5-layer security     │
└────────────────────┴─────────────────────┴──────────────────────┘
```

---

## Port Mapping

```
┌───────────────┬──────┬────────────────────────────┐
│  Service      │ Port │  Description               │
├───────────────┼──────┼────────────────────────────┤
│ Frontend      │ 3000 │ React dev server           │
│ Backend       │ 8000 │ FastAPI application        │
│ PostgreSQL    │ 5432 │ Database                   │
│ Qdrant        │ 6333 │ Vector DB API              │
│ Qdrant UI     │ 6334 │ Admin dashboard            │
│ TEI           │ 8080 │ Embedding service          │
│ Redis         │ 6379 │ Cache server               │
│ Nginx (Prod)  │  80  │ HTTP                       │
│ Nginx (Prod)  │ 443  │ HTTPS                      │
│ Ollama (Host) │11434 │ LLM inference              │
└───────────────┴──────┴────────────────────────────┘
```

---

This architecture provides:
- ✅ Military-grade security (5-layer SMC)
- ✅ Deterministic, auditable operations
- ✅ Local-first privacy (with cloud fallback)
- ✅ Production-ready scalability
- ✅ Beautiful glass morphism UI
- ✅ Complete document analysis
- ✅ SMC memory container integration
