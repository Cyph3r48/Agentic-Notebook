# Structured Intelligence

## What This Is

A RAG (Retrieval-Augmented Generation) powered AI application that enables users to upload documents, chat with their content using local or API-based LLMs, and maintain secure conversations with full audit trails. Built with FastAPI backend and React frontend featuring a glass morphism design system.

## Core Value

Users can securely upload documents and get accurate, citation-backed answers from their content using AI, with complete privacy and auditability.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] User authentication with JWT (signup, login, password reset)
- [ ] Document upload and management (PDF, DOCX, Markdown)
- [ ] Document chunking and embedding generation
- [ ] Semantic search across documents
- [ ] Chat interface with RAG (Retrieval-Augmented Generation)
- [ ] Citation-backed AI responses
- [ ] 5-Layer SMC security implementation (PI Guard, Sanitizer, Resolver, Tool Whitelist, CIFS Audit)
- [ ] Glass morphism UI design system
- [ ] Vector database integration (Qdrant)
- [ ] Local LLM support via Ollama (llama3.2, gemma2, qwen2.5)
- [ ] Optional Claude API integration
- [ ] Analytics dashboard
- [ ] User settings and preferences
- [ ] Role-based access control (admin, user, viewer)

### Out of Scope

- Real-time chat/websocket — defer to future version
- Mobile apps (iOS, Android) — web-first approach
- Browser extension — not core to v1
- Audio/video generation — complex feature, defer to v2
- SSO/SAML — email/password sufficient for v1
- Multi-tenancy — single tenant for v1

## Context

**Technical Environment:**
- Backend: FastAPI (Python 3.11+) with async support
- Frontend: React 18+ with Vite, Tailwind CSS, Framer Motion
- Database: PostgreSQL 15+ with asyncpg
- Vector DB: Qdrant for semantic search
- Cache: Redis for sessions
- LLMs: Ollama (local) + Claude API (optional)
- Embedding: TEI with BAAI/bge-large-en-v1.5
- Deployment: Docker Compose (local/VPS), Kubernetes (scalable)

**Security Context:**
- 5-Layer SMC architecture for defense in depth
- Layer 1: PI Guard (prompt injection detection)
- Layer 2: Sanitizer (content cleaning)
- Layer 3: Resolver (integrity verification with SHA-256)
- Layer 4: Tool Whitelist (RBAC)
- Layer 5: CIFS Audit (comprehensive logging)

**Design System:**
- Glass morphism: frosted glass cards with blur effects
- Color palette: deep navy (#0a0e1a), primary blue (#0066ff), Claude orange (#ff9933)
- Typography: Space Grotesk (display), Inter (body), JetBrains Mono (code)
- Animations: Framer Motion for smooth transitions

## Constraints

- **Tech Stack**: Must use FastAPI + React as specified in architecture
- **Security**: Must implement all 5 SMC layers before any user-facing features
- **Privacy**: Local LLM support mandatory (Ollama), Claude API optional
- **Performance**: Target <100ms vector search, <50 tokens/sec LLM response
- **Deployment**: Docker Compose must work on standard VPS (4GB RAM minimum)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Local-first LLM approach | Privacy and cost — users can run without API keys | — Pending |
| 5-Layer SMC security | Defense in depth, auditability, tamper detection | — Pending |
| Glass morphism UI | Modern, professional aesthetic with accessibility | — Pending |
| PostgreSQL + Qdrant | Relational + vector search best of both worlds | — Pending |
| Docker Compose deployment | Simplest path to production for self-hosting | — Pending |

---
*Last updated: 2026-02-12 after initialization*
