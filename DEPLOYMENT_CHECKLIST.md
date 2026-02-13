# 🚀 Structured Intelligence - Deployment Checklist

## ✅ Pre-Deployment

### System Requirements
- [ ] Docker 20.10+ installed
- [ ] Docker Compose v2.0+ installed
- [ ] 8GB+ RAM available (16GB recommended)
- [ ] 10GB+ disk space free
- [ ] Ollama installed and running
- [ ] At least one Ollama model pulled

### Security Setup
- [ ] Generated secure `JWT_SECRET` (32+ chars)
- [ ] Changed `PGPASSWORD` from default
- [ ] Changed `REDIS_PASSWORD` from default
- [ ] Set unique `ADMIN_EMAIL` and `ADMIN_PASSWORD`
- [ ] Configured `SMC_ADMIN_TOKEN` (if using existing SMC)

### Configuration Review
- [ ] Reviewed `.env` file completely
- [ ] Selected appropriate `DEFAULT_MODEL` for hardware
- [ ] Configured `CORS_ORIGINS` for your domain
- [ ] Set `MAX_UPLOAD_SIZE_MB` appropriately
- [ ] Reviewed `ALLOWED_EXTENSIONS`

---

## 🏗️ Deployment Steps

### 1. Initial Setup
```bash
# Extract archive
tar -xzf structured-intelligence-complete.tar.gz
cd structured-intelligence

# Create environment file
cp .env.template .env
nano .env  # Edit with your settings

# Make script executable
chmod +x quick-start.sh
```

### 2. Ollama Configuration
```bash
# Check Ollama status
ollama list

# Pull recommended model (based on your RAM)
# For laptop (8-16GB):
ollama pull llama3.2:3b-instruct-q4_K_M

# For desktop (32GB+):
ollama pull gemma2:9b
# or
ollama pull qwen2.5:14b

# Verify model
ollama run llama3.2:3b-instruct-q4_K_M "Hello"
```

### 3. Launch Application
```bash
# Option 1: Quick start (automated)
./quick-start.sh

# Option 2: Manual (development)
docker compose build
docker compose up -d

# Option 3: Manual (production with Nginx)
docker compose --profile production build
docker compose --profile production up -d
```

### 4. Verify Services
```bash
# Check all containers are running
docker compose ps

# Expected output:
# - si-postgres (healthy)
# - si-qdrant (healthy)
# - si-tei (healthy)
# - si-redis (healthy)
# - si-backend (healthy)
# - si-frontend (healthy)

# Check backend health
curl http://localhost:8000/health

# Check Qdrant
curl http://localhost:6333/healthz
```

---

## 🔐 Post-Deployment Security

### Immediate Actions
- [ ] Login at http://localhost:3000
- [ ] **Change admin password immediately**
- [ ] Create additional user accounts (if team deployment)
- [ ] Test document upload
- [ ] Test chat functionality
- [ ] Verify audit logs are working

### Security Hardening (Production)
- [ ] Enable HTTPS (configure Nginx SSL)
- [ ] Configure firewall rules
- [ ] Set up automated backups
- [ ] Enable monitoring/alerting
- [ ] Review audit logs regularly
- [ ] Implement rate limiting at network level
- [ ] Configure fail2ban (optional)
- [ ] Set up log rotation

### SSL/TLS Setup (Production)
```bash
# Generate self-signed cert (development)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/key.pem \
  -out nginx/ssl/cert.pem

# Or use Let's Encrypt (production)
# Install certbot and configure for your domain
```

---

## 📊 Monitoring & Maintenance

### Daily Checks
- [ ] Check container health: `docker compose ps`
- [ ] Review error logs: `docker compose logs --tail=100`
- [ ] Monitor disk usage: `df -h`
- [ ] Check memory usage: `free -h`

### Weekly Tasks
- [ ] Review audit logs for security events
- [ ] Check backup integrity
- [ ] Monitor vector DB size
- [ ] Review user activity

### Monthly Tasks
- [ ] Update Docker images: `docker compose pull`
- [ ] Rotate admin tokens
- [ ] Review and archive old logs
- [ ] Performance testing
- [ ] Security audit

---

## 🔄 Backup & Recovery

### Database Backup
```bash
# Backup PostgreSQL
docker exec si-postgres pg_dump -U si_user structured_intelligence > backup.sql

# Backup with compression
docker exec si-postgres pg_dump -U si_user structured_intelligence | gzip > backup.sql.gz

# Automated daily backup (cron)
0 2 * * * docker exec si-postgres pg_dump -U si_user structured_intelligence | gzip > /backups/si-$(date +\%Y\%m\%d).sql.gz
```

### Vector DB Backup
```bash
# Backup Qdrant snapshots
docker exec si-qdrant curl -X POST http://localhost:6333/collections/si_documents/snapshots

# Download snapshot
docker cp si-qdrant:/qdrant/storage/snapshots /backups/qdrant/
```

### Full System Backup
```bash
# Stop containers
docker compose down

# Backup volumes
docker run --rm -v si_postgres_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/postgres_backup.tar.gz /data

docker run --rm -v si_qdrant_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/qdrant_backup.tar.gz /data

# Restart
docker compose up -d
```

### Recovery Procedure
```bash
# 1. Stop containers
docker compose down

# 2. Restore volumes
docker run --rm -v si_postgres_data:/data -v $(pwd):/backup \
  alpine sh -c "cd /data && tar xzf /backup/postgres_backup.tar.gz --strip 1"

# 3. Restart
docker compose up -d
```

---

## 🐛 Troubleshooting

### Backend Won't Start
```bash
# Check logs
docker compose logs backend

# Common issues:
# - Database connection: Check PGPASSWORD in .env
# - Redis connection: Check REDIS_PASSWORD in .env
# - Port conflict: Change ports in docker-compose.yml
```

### Ollama Connection Failed
```bash
# Verify Ollama is running
curl http://localhost:11434/api/tags

# Check from inside container
docker exec -it si-backend curl http://host.docker.internal:11434/api/tags

# Fix: Ensure Ollama is running on host
```

### Vector Search Not Working
```bash
# Check Qdrant collection
curl http://localhost:6333/collections

# Check TEI embedding service
curl http://localhost:8080/health

# Verify embeddings are being generated
docker compose logs tei
```

### Frontend Build Errors
```bash
# Clear node_modules and rebuild
docker compose down frontend
docker compose build --no-cache frontend
docker compose up -d frontend
```

---

## 📈 Performance Optimization

### For Laptop/Limited RAM
```bash
# Use smaller model
DEFAULT_MODEL=llama3.2:3b-instruct-q4_K_M

# Reduce chunk size
CHUNK_SIZE=500
CHUNK_OVERLAP=100

# Lower concurrent workers
# In docker-compose.yml backend:
command: ["uvicorn", "app.main:app", "--workers", "1"]
```

### For GPU Server
```bash
# Use larger model
DEFAULT_MODEL=llama3.1:70b

# Increase chunk size for better context
CHUNK_SIZE=2000
CHUNK_OVERLAP=400

# More workers
command: ["uvicorn", "app.main:app", "--workers", "4"]
```

---

## 🔗 Integration with Existing SMC

### Network Configuration
```yaml
# In docker-compose.yml
networks:
  si_net:
    external: true
    name: kaiyi_net  # Your existing SMC network
```

### Environment Variables
```bash
# In .env
SMC_ENABLED=true
SMC_ADMIN_TOKEN=your_existing_smc_admin_token
SMC_POSTGRES_URL=postgresql://kaiyi_user:password@smc-postgres:5432/kaiyi
QDRANT_URL=http://smc-qdrant:6333
```

### Verification
```bash
# Test SMC connection
docker exec -it si-backend python -c "
from app.services.smc_service import smc_service
import asyncio
result = asyncio.run(smc_service.pi_guard_check('test'))
print(result)
"
```

---

## ✅ Final Checklist

### Before Going Live
- [ ] All security settings configured
- [ ] Admin password changed
- [ ] Backups automated and tested
- [ ] Monitoring configured
- [ ] SSL/TLS enabled (production)
- [ ] Firewall rules set
- [ ] Rate limiting tested
- [ ] Load testing completed
- [ ] Disaster recovery tested
- [ ] Documentation reviewed

### Production Ready
- [ ] ENVIRONMENT=production in .env
- [ ] DEBUG=false in .env
- [ ] CORS_ORIGINS set to production domain
- [ ] Logs configured and rotated
- [ ] Metrics dashboard set up
- [ ] Alerting configured
- [ ] Team trained on system
- [ ] Runbook created

---

**Deployment completed! 🎉**

For support, see:
- README.md for general documentation
- PROJECT_OVERVIEW.md for architecture details
- Docker logs: `docker compose logs -f`
- Health check: http://localhost:8000/health
