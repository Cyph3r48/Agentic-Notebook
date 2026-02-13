# 🎯 Structured Intelligence - Quick Reference

## 🚀 60-Second Deploy

```bash
# 1. Extract
tar -xzf structured-intelligence-complete.tar.gz
cd structured-intelligence

# 2. Configure
cp .env.template .env
nano .env  # Change passwords & settings

# 3. Install Ollama model
ollama pull llama3.2:3b-instruct-q4_K_M

# 4. Launch
./quick-start.sh

# 5. Access
# http://localhost:3000
```

---

## 🎨 Design System

### Colors (in Tailwind classes)
- **Background**: `bg-dark-base` (#0a0e1a)
- **Primary**: `bg-blue-500` (#0066ff)
- **Purple**: `bg-purple-500` (#9966ff)
- **Orange**: `bg-claude-orange-500` (#ff9933)
- **Glass**: `bg-glass-white` with `backdrop-blur-xl`

### Glass Card Template
```jsx
<div className="bg-glass-white backdrop-blur-xl border border-glass-border rounded-2xl p-6 shadow-glass">
  {/* Your content */}
</div>
```

### Animations
```jsx
<motion.div
  initial={{ opacity: 0, y: 20 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ duration: 0.5 }}
>
  {/* Animated element */}
</motion.div>
```

---

## 🔐 SMC Security Quick Ref

### Layer 1: PI Guard
```python
# Check for adversarial patterns
result = await smc_service.pi_guard_check(user_input)
if not result["passed"]:
    # Block request
```

### Layer 2: Sanitizer
```python
# Clean content
sanitized = await smc_service.sanitize_content(content, "html")
```

### Layer 3: Resolver
```python
# Verify integrity
content_hash = smc_service.compute_hash(content)
valid = await smc_service.verify_integrity(content, expected_hash)
```

### Layer 4: Tool Whitelist
```python
# Check permission
allowed = await smc_service.check_tool_permission(
    tool_name="delete_document",
    user_role="admin",
    admin_token=admin_token
)
```

### Layer 5: CIFS Audit
```python
# Log action
request_id = await smc_service.audit_log(
    user_id=user.id,
    action="document_upload",
    resource_type="document",
    resource_id=doc.id
)
```

---

## 📊 Essential Commands

### Docker Management
```bash
# Start
docker compose up -d

# Stop
docker compose down

# Restart
docker compose restart

# Logs (all)
docker compose logs -f

# Logs (specific)
docker compose logs -f backend
docker compose logs -f frontend

# Rebuild
docker compose build --no-cache
docker compose up -d --force-recreate

# Clean up
docker compose down -v  # Warning: deletes volumes!
```

### Database Operations
```bash
# Enter PostgreSQL
docker exec -it si-postgres psql -U si_user structured_intelligence

# Backup
docker exec si-postgres pg_dump -U si_user structured_intelligence > backup.sql

# Restore
cat backup.sql | docker exec -i si-postgres psql -U si_user structured_intelligence
```

### Ollama Management
```bash
# List models
ollama list

# Pull model
ollama pull llama3.2:3b-instruct-q4_K_M

# Remove model
ollama rm llama3.2:3b-instruct-q4_K_M

# Test model
ollama run llama3.2:3b-instruct-q4_K_M "Hello"

# Check status
curl http://localhost:11434/api/tags
```

---

## 🌐 API Endpoints

### Authentication
```bash
# Login
POST /api/v1/auth/login
{
  "email": "admin@example.com",
  "password": "password"
}

# Refresh token
POST /api/v1/auth/refresh
Authorization: Bearer <token>
```

### Documents
```bash
# Upload
POST /api/v1/documents/upload
Content-Type: multipart/form-data
file: <file>

# List
GET /api/v1/documents

# Delete
DELETE /api/v1/documents/{id}
```

### Chat
```bash
# Create conversation
POST /api/v1/chat/conversations
{
  "title": "New Chat",
  "model": "llama3.2:3b-instruct-q4_K_M"
}

# Send message
POST /api/v1/chat/conversations/{id}/messages
{
  "content": "What is in my documents?",
  "use_rag": true
}
```

### Search
```bash
# Semantic search
POST /api/v1/search
{
  "query": "machine learning",
  "limit": 5
}
```

---

## 🔧 Environment Variables (Key Ones)

### Required
```bash
PGPASSWORD=                # Secure password
REDIS_PASSWORD=            # Secure password
JWT_SECRET=                # 32+ char secret
ADMIN_EMAIL=               # Your email
ADMIN_PASSWORD=            # Change after first login
```

### LLM Configuration
```bash
OLLAMA_URL=http://host.docker.internal:11434
DEFAULT_MODEL=llama3.2:3b-instruct-q4_K_M
CLAUDE_API_KEY=            # Optional
```

### SMC Integration
```bash
SMC_ENABLED=true
SMC_ADMIN_TOKEN=           # Your SMC token
SMC_PI_GUARD_ENABLED=true
SMC_SANITIZER_ENABLED=true
SMC_RESOLVER_ENABLED=true
SMC_TOOL_WHITELIST_ENABLED=true
SMC_CIFS_AUDIT_ENABLED=true
```

---

## 🎯 Model Recommendations

### Hardware-Based Selection

| RAM    | Model                           | Speed        | Quality |
|--------|----------------------------------|--------------|---------|
| 8GB    | llama3.2:3b-instruct-q4_K_M     | Fast         | Good    |
| 16GB   | gemma2:9b                       | Medium       | Better  |
| 32GB   | qwen2.5:14b                     | Medium-Slow  | Great   |
| 48GB+  | llama3.1:70b (GPU)              | Slow         | Best    |

---

## 📱 UI Navigation

```
Login → Dashboard → [5 Main Sections]
                    │
                    ├─ Documents (upload, manage)
                    ├─ Chat (RAG conversations)
                    ├─ Search (semantic search)
                    ├─ Analytics (usage stats)
                    └─ Settings (profile, preferences)
```

---

## 🐛 Common Issues & Fixes

### Issue: Backend won't start
```bash
# Fix: Check database connection
docker compose logs postgres
# Verify PGPASSWORD in .env
```

### Issue: Ollama connection failed
```bash
# Fix: Ensure Ollama is running
ollama list
# Check from container
docker exec -it si-backend curl http://host.docker.internal:11434/api/tags
```

### Issue: Frontend blank page
```bash
# Fix: Check VITE_API_URL
# In .env: VITE_API_URL=http://localhost:8000
docker compose restart frontend
```

### Issue: Vector search returns no results
```bash
# Fix: Check Qdrant collection
curl http://localhost:6333/collections
# Verify documents were processed
docker compose logs backend | grep "Processing document"
```

---

## 📊 Performance Tuning

### Laptop (8-16GB)
```bash
DEFAULT_MODEL=llama3.2:3b-instruct-q4_K_M
CHUNK_SIZE=500
CHUNK_OVERLAP=100
```

### Desktop (32GB+)
```bash
DEFAULT_MODEL=qwen2.5:14b
CHUNK_SIZE=2000
CHUNK_OVERLAP=400
```

### GPU Server
```bash
DEFAULT_MODEL=llama3.1:70b
CHUNK_SIZE=2000
CHUNK_OVERLAP=400
# In docker-compose.yml: workers: 4
```

---

## 🔐 Security Checklist

- [ ] Changed all default passwords
- [ ] JWT_SECRET is 32+ random characters
- [ ] Admin password changed after first login
- [ ] HTTPS enabled (production)
- [ ] Firewall configured
- [ ] Backups automated
- [ ] Audit logs monitored
- [ ] Rate limiting enabled

---

## 📞 Quick Links

- **Frontend**: http://localhost:3000
- **Backend**: http://localhost:8000
- **API Docs**: http://localhost:8000/api/docs
- **Qdrant**: http://localhost:6333/dashboard
- **Health**: http://localhost:8000/health

---

**Need Help?**
- Check logs: `docker compose logs -f`
- Review docs: `README.md`, `PROJECT_OVERVIEW.md`
- Deployment guide: `DEPLOYMENT_CHECKLIST.md`
