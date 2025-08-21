# Docker Images with Claude OAuth Support

This directory contains Docker configurations for LiteLLM with integrated Claude OAuth authentication support.

## Available Images

### Main Image (`litellm/litellm`)
The primary LiteLLM proxy server with full Claude OAuth support.

```bash
docker pull ghcr.io/tom130/litellm:main
```

**Features:**
- Claude OAuth PKCE authentication
- Automatic token refresh
- Multi-user token management
- Encrypted token storage
- Support for all LiteLLM features

### Database Image (`litellm/litellm-database`)
LiteLLM with PostgreSQL integration for persistent OAuth token storage.

```bash
docker pull ghcr.io/tom130/litellm-database:main
```

**Features:**
- PostgreSQL database included
- OAuth token persistence
- User management
- Audit logging

### Non-Root Image (`litellm/litellm-non-root`)
Security-hardened image running as non-root user.

```bash
docker pull ghcr.io/tom130/litellm-non-root:main
```

**Features:**
- Runs as UID 1000
- Read-only root filesystem compatible
- Suitable for Kubernetes with PSPs

## Quick Start with Claude OAuth

### 1. Using Docker Compose

```yaml
version: '3.8'

services:
  litellm:
    image: ghcr.io/tom130/litellm:main
    ports:
      - "4000:4000"
    environment:
      - DATABASE_URL=postgresql://litellm:password@postgres:5432/litellm
      - CLAUDE_OAUTH_CLIENT_ID=${CLAUDE_OAUTH_CLIENT_ID}
      - CLAUDE_OAUTH_REDIRECT_URI=http://localhost:4000/auth/claude/callback
      - CLAUDE_TOKEN_ENCRYPTION_KEY=${CLAUDE_TOKEN_ENCRYPTION_KEY}
      - MASTER_KEY=${MASTER_KEY:-sk-1234}
    volumes:
      - ./config.yaml:/app/config.yaml
    depends_on:
      - postgres
    restart: unless-stopped

  postgres:
    image: postgres:15-alpine
    environment:
      - POSTGRES_DB=litellm
      - POSTGRES_USER=litellm
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

volumes:
  postgres_data:
```

### 2. Using Docker Run

```bash
# Generate encryption key
export CLAUDE_TOKEN_ENCRYPTION_KEY=$(openssl rand -base64 32)

# Run LiteLLM with Claude OAuth
docker run -d \
  --name litellm \
  -p 4000:4000 \
  -e CLAUDE_OAUTH_CLIENT_ID="your-client-id" \
  -e CLAUDE_OAUTH_REDIRECT_URI="http://localhost:4000/auth/claude/callback" \
  -e CLAUDE_TOKEN_ENCRYPTION_KEY="${CLAUDE_TOKEN_ENCRYPTION_KEY}" \
  -e DATABASE_URL="sqlite:///app/litellm.db" \
  -v $(pwd)/config.yaml:/app/config.yaml \
  -v litellm_data:/app/data \
  ghcr.io/tom130/litellm:main
```

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `CLAUDE_OAUTH_CLIENT_ID` | OAuth client ID from Claude | Yes |
| `CLAUDE_OAUTH_REDIRECT_URI` | OAuth callback URL | Yes |
| `CLAUDE_TOKEN_ENCRYPTION_KEY` | AES-256 key for token encryption | Recommended |
| `DATABASE_URL` | Database connection string | Recommended |
| `MASTER_KEY` | LiteLLM master API key | Yes |

### config.yaml Example

```yaml
model_list:
  - model_name: claude-3-sonnet
    litellm_params:
      model: anthropic/claude-3-sonnet-4-20250514
      
  - model_name: claude-3-opus
    litellm_params:
      model: anthropic/claude-3-opus-4-20250805

general_settings:
  master_key: ${MASTER_KEY}
  enable_claude_oauth: true
  
claude_oauth:
  enabled: true
  client_id: ${CLAUDE_OAUTH_CLIENT_ID}
  redirect_uri: ${CLAUDE_OAUTH_REDIRECT_URI}
  scopes: ["claude:chat", "claude:models", "claude:read"]
  token_encryption: true
  auto_refresh: true
  refresh_threshold: 300
```

## Building Images Locally

### Build Main Image

```bash
docker build -t litellm:local .
```

### Build with Specific Features

```bash
# With Claude OAuth debug mode
docker build \
  --build-arg ENABLE_OAUTH_DEBUG=true \
  -t litellm:oauth-debug .

# With custom Python version
docker build \
  --build-arg LITELLM_BUILD_IMAGE=python:3.11-slim \
  -t litellm:py311 .
```

### Multi-Platform Build

```bash
# Build for multiple architectures
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t litellm:multiarch \
  --push .
```

## OAuth Authentication Flow

1. **Initial Setup**
   ```bash
   # Start the container
   docker-compose up -d
   
   # Check OAuth health
   curl http://localhost:4000/auth/claude/health
   ```

2. **User Authentication**
   ```bash
   # Get authorization URL
   curl http://localhost:4000/auth/claude/authorize \
     -H "Authorization: Bearer YOUR_LITELLM_KEY"
   ```

3. **Using Claude Models**
   ```bash
   # After OAuth authentication
   curl -X POST http://localhost:4000/chat/completions \
     -H "Authorization: Bearer YOUR_LITELLM_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "model": "claude-3-sonnet",
       "messages": [{"role": "user", "content": "Hello!"}]
     }'
   ```

## Database Migrations

When using PostgreSQL, run migrations on first start:

```bash
# Using docker exec
docker exec litellm prisma migrate deploy

# Or include in startup script
docker run --rm \
  -e DATABASE_URL="postgresql://..." \
  ghcr.io/tom130/litellm:main \
  prisma migrate deploy
```

## Security Considerations

### Production Deployment

1. **Use HTTPS**: Always use HTTPS for OAuth redirect URIs in production
2. **Secure Keys**: Store encryption keys in secrets management (Kubernetes Secrets, Docker Secrets, etc.)
3. **Network Isolation**: Use Docker networks to isolate database from public access
4. **Regular Updates**: Pull latest images regularly for security patches

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: litellm
spec:
  replicas: 2
  selector:
    matchLabels:
      app: litellm
  template:
    metadata:
      labels:
        app: litellm
    spec:
      containers:
      - name: litellm
        image: ghcr.io/tom130/litellm-non-root:main
        ports:
        - containerPort: 4000
        env:
        - name: CLAUDE_OAUTH_CLIENT_ID
          valueFrom:
            secretKeyRef:
              name: litellm-oauth
              key: client-id
        - name: CLAUDE_TOKEN_ENCRYPTION_KEY
          valueFrom:
            secretKeyRef:
              name: litellm-oauth
              key: encryption-key
        securityContext:
          runAsNonRoot: true
          runAsUser: 1000
          readOnlyRootFilesystem: true
```

## Monitoring

### Health Checks

```yaml
# docker-compose.yml
services:
  litellm:
    # ... other config ...
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:4000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

### Logging

```bash
# View logs
docker logs litellm

# Follow logs
docker logs -f litellm

# Filter OAuth logs
docker logs litellm 2>&1 | grep -i oauth
```

## Troubleshooting

### Common Issues

**Container fails to start**
```bash
# Check logs
docker logs litellm

# Verify environment variables
docker exec litellm env | grep CLAUDE
```

**OAuth callback fails**
- Ensure `CLAUDE_OAUTH_REDIRECT_URI` matches exactly in both environment and Claude OAuth settings
- Check network connectivity from container

**Token refresh errors**
```bash
# Check token manager status
curl http://localhost:4000/auth/claude/health

# Manually refresh token
curl -X POST http://localhost:4000/auth/claude/refresh \
  -H "Authorization: Bearer YOUR_KEY"
```

## CI/CD Integration

The Docker images are automatically built and pushed when:
- Code is pushed to `main` branch
- A new release is tagged
- Manually triggered via GitHub Actions

### Image Tags

- `main` - Latest from main branch
- `main-{sha}` - Specific commit
- `main-{date}` - Date-based tag (YYYYMMDD)
- `main-claude-oauth` - Latest with OAuth support

## Support

- [GitHub Issues](https://github.com/tom130/litellm/issues)
- [LiteLLM Documentation](https://docs.litellm.ai)
- [Docker Hub](https://hub.docker.com/r/tom130/litellm)