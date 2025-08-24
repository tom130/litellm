# Docker Images with Claude OAuth Support

This directory contains Docker configurations for LiteLLM with integrated Claude OAuth authentication support.

## Available Images

### Main Image (`litellm/litellm`)
The primary LiteLLM proxy server with full Claude OAuth support.

```bash
docker pull ghcr.io/berriai/litellm:main-stable
```

**Features:**
- Claude OAuth 2.0 + PKCE authentication flow
- Automatic token refresh before expiration
- Database storage with AES-256 encryption
- Multi-user token management with isolation
- Storage hierarchy: Database → Cache → File → Environment
- All standard LiteLLM features

### Database Image (`litellm/litellm-database`)
LiteLLM with PostgreSQL integration for persistent OAuth token storage.

```bash
docker pull ghcr.io/berriai/litellm-database:main
```

**Features:**
- PostgreSQL database for token persistence
- OAuth token encryption and secure storage
- Per-user token isolation
- Audit logging with timestamps
- Automatic token refresh tracking

## Quick Start with Claude OAuth

### 1. Using Docker Compose (Recommended)

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  litellm:
    image: ghcr.io/berriai/litellm:main-stable
    ports:
      - "4000:4000"
    environment:
      DATABASE_URL: "postgresql://llmproxy:dbpassword@db:5432/litellm"
      CLAUDE_TOKEN_ENCRYPTION_KEY: "${CLAUDE_TOKEN_ENCRYPTION_KEY}"
      LITELLM_MASTER_KEY: "${LITELLM_MASTER_KEY}"
    volumes:
      - ./config.yaml:/app/config.yaml
      - oauth_tokens:/app/.litellm  # Fallback file storage
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped

  db:
    image: postgres:16
    environment:
      POSTGRES_DB: litellm
      POSTGRES_USER: llmproxy
      POSTGRES_PASSWORD: dbpassword
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./migrations/add_claude_oauth_tokens.sql:/docker-entrypoint-initdb.d/01-oauth.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U llmproxy -d litellm"]
      interval: 5s
      retries: 10
    restart: unless-stopped

volumes:
  postgres_data:
  oauth_tokens:
```

### 2. Environment Configuration

Create `.env` file:

```bash
# Database (for persistent storage)
DATABASE_URL=postgresql://llmproxy:dbpassword@db:5432/litellm

# OAuth Security
CLAUDE_TOKEN_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# LiteLLM Master Key
LITELLM_MASTER_KEY=sk-your-secure-master-key

# Optional: Pre-existing tokens (for migration)
CLAUDE_ACCESS_TOKEN=
CLAUDE_REFRESH_TOKEN=
CLAUDE_EXPIRES_AT=
```

### 3. Configuration File

Create `config.yaml`:

```yaml
model_list:
  - model_name: claude-3-opus
    litellm_params:
      model: claude-3-opus-20240229
      api_key: "oauth"  # Indicates OAuth authentication
      
  - model_name: claude-3-sonnet
    litellm_params:
      model: claude-3-sonnet-20240229
      api_key: "oauth"

general_settings:
  database_url: "${DATABASE_URL}"
  master_key: "${LITELLM_MASTER_KEY}"

# OAuth configuration
claude_oauth:
  enabled: true
  token_file: "~/.litellm/claude_tokens.json"  # Fallback when DB unavailable
  encryption_key: "${CLAUDE_TOKEN_ENCRYPTION_KEY}"
  auto_refresh: true
  refresh_buffer: 300  # Refresh 5 minutes before expiration
  use_database: true  # Enable database storage
```

### 4. Start Services

```bash
# Start containers
docker-compose up -d

# Check health
docker-compose ps

# View logs
docker-compose logs -f litellm
```

## OAuth Authentication Flow in Docker

### Initial Authentication

1. **Start OAuth flow inside container:**
```bash
docker exec -it litellm-litellm-1 python -m litellm.proxy.auth.claude_oauth_cli login
```

2. **Visit the displayed URL in your browser**

3. **Complete authentication with the code:**
```bash
docker exec -it litellm-litellm-1 python -m litellm.proxy.auth.claude_oauth_cli callback <CODE>
```

4. **Check status:**
```bash
docker exec -it litellm-litellm-1 python -m litellm.proxy.auth.claude_oauth_cli status
```

### Using the API

Once authenticated, use Claude models through the proxy:

```bash
curl -X POST http://localhost:4000/chat/completions \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-opus",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## Database Migration

The OAuth tokens table is automatically created on first run if using the docker-compose setup above.

### Manual Migration

If needed, run the migration manually:

```bash
# Copy migration file into container
docker cp migrations/add_claude_oauth_tokens.sql litellm-db-1:/tmp/

# Run migration
docker exec litellm-db-1 psql -U llmproxy -d litellm -f /tmp/add_claude_oauth_tokens.sql

# Verify table creation
docker exec litellm-db-1 psql -U llmproxy -d litellm -c "\dt \"LiteLLM_ClaudeOAuthTokens\""
```

## Token Storage Hierarchy

LiteLLM uses a hierarchical storage system:

1. **Database (Primary)** - PostgreSQL with encryption
   - Per-user token isolation
   - Audit trail with timestamps
   - Automatic refresh tracking

2. **Cache (Performance)** - Redis/In-memory
   - Fast token retrieval
   - TTL-based expiration

3. **File (Fallback)** - Local filesystem
   - Location: `/app/.litellm/claude_tokens.json`
   - Used when database unavailable
   - 0600 permissions for security

4. **Environment (Legacy)** - Environment variables
   - `CLAUDE_ACCESS_TOKEN`
   - `CLAUDE_REFRESH_TOKEN`
   - `CLAUDE_EXPIRES_AT`

## Security Best Practices

### Production Deployment

1. **Use strong encryption keys:**
```bash
# Generate secure key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

2. **Secure database connection:**
```yaml
environment:
  DATABASE_URL: "postgresql://user:${DB_PASSWORD}@db:5432/litellm?sslmode=require"
```

3. **Use Docker secrets:**
```yaml
secrets:
  claude_encryption_key:
    external: true
  db_password:
    external: true

services:
  litellm:
    secrets:
      - claude_encryption_key
      - db_password
```

4. **Network isolation:**
```yaml
networks:
  backend:
    internal: true
  frontend:
    external: true
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: litellm
spec:
  replicas: 2
  template:
    spec:
      containers:
      - name: litellm
        image: ghcr.io/berriai/litellm:main-stable
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: litellm-db
              key: connection-string
        - name: CLAUDE_TOKEN_ENCRYPTION_KEY
          valueFrom:
            secretKeyRef:
              name: litellm-oauth
              key: encryption-key
        volumeMounts:
        - name: config
          mountPath: /app/config.yaml
          subPath: config.yaml
      volumes:
      - name: config
        configMap:
          name: litellm-config
```

## Monitoring and Health Checks

### Docker Compose Health Check

```yaml
services:
  litellm:
    healthcheck:
      test: ["CMD", "python", "-m", "litellm.proxy.auth.claude_oauth_cli", "status"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

### Manual Health Check

```bash
# Check OAuth status
docker exec litellm-litellm-1 python -m litellm.proxy.auth.claude_oauth_cli status

# Check database connection
docker exec litellm-db-1 pg_isready -U llmproxy -d litellm

# View token records
docker exec litellm-db-1 psql -U llmproxy -d litellm -c "SELECT user_id, expires_at, refresh_count FROM \"LiteLLM_ClaudeOAuthTokens\";"
```

## Troubleshooting

### Common Issues

**Container fails to start:**
```bash
# Check logs
docker-compose logs litellm

# Verify environment variables
docker exec litellm-litellm-1 env | grep -E "CLAUDE|DATABASE"
```

**Database connection errors:**
```bash
# Test database connection
docker exec litellm-db-1 pg_isready

# Check if table exists
docker exec litellm-db-1 psql -U llmproxy -d litellm -c "\dt"
```

**OAuth authentication fails:**
```bash
# Clear tokens and restart
docker exec litellm-litellm-1 rm -f /app/.litellm/claude_tokens.json
docker exec litellm-litellm-1 python -m litellm.proxy.auth.claude_oauth_cli logout
docker-compose restart litellm
```

**Token refresh errors:**
```bash
# Check token expiration
docker exec litellm-db-1 psql -U llmproxy -d litellm -c "SELECT user_id, expires_at, CASE WHEN expires_at > NOW() THEN 'valid' ELSE 'expired' END as status FROM \"LiteLLM_ClaudeOAuthTokens\";"

# Force token refresh
docker exec litellm-litellm-1 python -m litellm.proxy.auth.claude_oauth_cli refresh
```

### Logging

```bash
# View all logs
docker-compose logs

# Follow specific service logs
docker-compose logs -f litellm

# Filter OAuth-related logs
docker-compose logs litellm | grep -i "oauth\|token\|claude"

# Enable debug logging
docker-compose exec litellm sh -c "export LITELLM_LOG_LEVEL=DEBUG && python -m litellm"
```

## Backup and Recovery

### Backup OAuth Tokens

```bash
# Database backup
docker exec litellm-db-1 pg_dump -U llmproxy -d litellm -t "\"LiteLLM_ClaudeOAuthTokens\"" > oauth_tokens_backup.sql

# File backup (if using file storage)
docker cp litellm-litellm-1:/app/.litellm/claude_tokens.json ./claude_tokens_backup.json
```

### Restore OAuth Tokens

```bash
# Database restore
docker cp oauth_tokens_backup.sql litellm-db-1:/tmp/
docker exec litellm-db-1 psql -U llmproxy -d litellm -f /tmp/oauth_tokens_backup.sql

# File restore
docker cp ./claude_tokens_backup.json litellm-litellm-1:/app/.litellm/claude_tokens.json
docker exec litellm-litellm-1 chmod 600 /app/.litellm/claude_tokens.json
```

## Multi-User Support

With database storage, each user has isolated OAuth tokens:

```sql
-- View all user tokens
SELECT 
    u.user_id,
    u.user_email,
    t.expires_at,
    t.refresh_count,
    CASE 
        WHEN t.expires_at > NOW() THEN 'active'
        WHEN t.refresh_token_encrypted IS NOT NULL THEN 'expired_refreshable'
        ELSE 'expired'
    END AS status
FROM "LiteLLM_UserTable" u
LEFT JOIN "LiteLLM_ClaudeOAuthTokens" t ON u.user_id = t.user_id;
```

## Building Custom Images

### Build with OAuth Support

```bash
# Clone repository
git clone https://github.com/BerriAI/litellm.git
cd litellm

# Build image
docker build -t litellm:oauth-custom .

# Build multi-platform
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t litellm:oauth-multiarch \
  --push .
```

## Support

- [GitHub Issues](https://github.com/BerriAI/litellm/issues)
- [Documentation](https://docs.litellm.ai/docs/proxy/claude_oauth)
- [Discord Community](https://discord.gg/litellm)