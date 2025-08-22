# Testing Claude OAuth with Docker

This guide provides comprehensive instructions for testing the Claude OAuth implementation using Docker.

## Table of Contents
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Detailed Setup](#detailed-setup)
- [OAuth Authentication Flow](#oauth-authentication-flow)
- [Testing API Endpoints](#testing-api-endpoints)
- [Troubleshooting](#troubleshooting)
- [Advanced Testing](#advanced-testing)

## Prerequisites

### Required Software
- Docker (version 20.10 or later)
- Docker Compose (version 2.0 or later)
- curl or httpie for API testing
- A Claude account with OAuth access

### Required Files
Ensure you have the following files in your project directory:
- `config.oauth.yaml` - LiteLLM configuration with OAuth models
- `.env.oauth` - Environment variables
- `docker-compose.test-oauth.yml` - Docker Compose configuration
- `test_oauth_docker.sh` - Automated test script

## Quick Start

### 1. Automated Testing
Run the automated test script:
```bash
./test_oauth_docker.sh
```

This script will:
- Check prerequisites
- Build and start containers
- Test OAuth endpoints
- Guide you through authentication
- Test API calls

### 2. Manual Quick Start
```bash
# Start containers
docker-compose -f docker-compose.test-oauth.yml --env-file .env.oauth up -d --build

# Check status
docker-compose -f docker-compose.test-oauth.yml ps

# View logs
docker-compose -f docker-compose.test-oauth.yml logs -f litellm
```

## Detailed Setup

### Step 1: Configure Environment

1. Copy the example environment file:
```bash
cp .env.oauth .env.oauth.local
```

2. Edit `.env.oauth.local` and set your preferences:
```env
LITELLM_MASTER_KEY=your-secure-key-here
CLAUDE_TOKEN_ENCRYPTION_KEY=$(openssl rand -hex 32)
```

### Step 2: Build and Start Services

```bash
# Build images
docker-compose -f docker-compose.test-oauth.yml build

# Start services in detached mode
docker-compose -f docker-compose.test-oauth.yml up -d

# Wait for services to be ready
sleep 10

# Check health
curl http://localhost:4000/health
```

### Step 3: Verify Services

Check that all services are running:
```bash
# Check container status
docker ps

# Check LiteLLM logs
docker logs litellm-litellm-1

# Check database
docker exec litellm-db-1 psql -U llmproxy -d litellm -c "\dt"

# Check Redis
docker exec litellm-redis-1 redis-cli ping
```

## OAuth Authentication Flow

### Method 1: CLI Authentication (Recommended)

1. **Start OAuth login:**
```bash
docker exec -it litellm-litellm-1 litellm claude login
```

Output:
```
🔐 Starting Claude OAuth authentication...
============================================================

📋 Authorization URL generated!
🌐 Opening browser...

============================================================
📝 After authorization, you'll be redirected to:
   https://console.anthropic.com/oauth/code/callback

⚠️  Copy the CODE parameter from the redirect URL

💡 Then run:
   litellm claude callback <CODE>
============================================================
```

2. **Open the authorization URL in your browser**
   - Sign in to Claude
   - Authorize the application
   - You'll be redirected to the Claude Console

3. **Complete authentication:**
```bash
# The redirect URL will look like:
# https://console.anthropic.com/oauth/code/callback?code=ABC123&state=XYZ789

# Copy the code (ABC123 in this example) and run:
docker exec -it litellm-litellm-1 litellm claude callback ABC123
```

4. **Verify authentication:**
```bash
docker exec -it litellm-litellm-1 litellm claude status
```

Expected output:
```
🔍 Claude OAuth Status
============================================================
✅ Using tokens from: /app/.litellm/claude_tokens.json

📊 Token Status:
   • Status: ✅ Valid
   • Expires in: 23.5 hours
```

### Method 2: API Authentication

1. **Start OAuth flow:**
```bash
curl http://localhost:4000/auth/claude/oauth/start
```

Response:
```json
{
  "authorization_url": "https://claude.ai/oauth/authorize?...",
  "state": "random_state_123"
}
```

2. **Visit the authorization URL and complete authentication**

3. **Exchange code for tokens:**
```bash
curl -X POST http://localhost:4000/auth/claude/oauth/exchange \
  -H "Content-Type: application/json" \
  -d '{
    "code": "YOUR_AUTH_CODE",
    "state": "random_state_123"
  }'
```

4. **Check status:**
```bash
curl http://localhost:4000/auth/claude/oauth/status
```

## Testing API Endpoints

### 1. List Available Models
```bash
curl -H "Authorization: Bearer sk-oauth-test-1234" \
  http://localhost:4000/v1/models | jq
```

Expected models:
- claude-opus-4.1
- claude-opus-4
- claude-sonnet-4
- claude-sonnet-3.7
- claude-haiku-3.5

### 2. Test Chat Completion
```bash
curl -X POST http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-oauth-test-1234" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-haiku-3.5",
    "messages": [
      {"role": "user", "content": "Hello, how are you?"}
    ],
    "max_tokens": 50
  }' | jq
```

### 3. Test with Different Models
```bash
# Test Claude Opus 4.1
curl -X POST http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-oauth-test-1234" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-opus-4.1",
    "messages": [
      {"role": "user", "content": "What is 2+2?"}
    ]
  }' | jq '.choices[0].message.content'

# Test Claude Sonnet 3.7
curl -X POST http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-oauth-test-1234" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-3.7",
    "messages": [
      {"role": "user", "content": "Write a haiku about OAuth"}
    ]
  }' | jq '.choices[0].message.content'
```

### 4. Test Streaming
```bash
curl -X POST http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-oauth-test-1234" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-haiku",
    "messages": [
      {"role": "user", "content": "Count to 5"}
    ],
    "stream": true
  }'
```

## Troubleshooting

### Common Issues

#### 1. OAuth Login Fails
```bash
# Check logs for errors
docker logs litellm-litellm-1 --tail 100

# Verify OAuth files are present
docker exec litellm-litellm-1 ls -la /app/litellm/proxy/auth/claude_oauth*

# Check Python imports
docker exec litellm-litellm-1 python -c "from litellm.proxy.auth.claude_oauth_flow import ClaudeOAuthFlow; print('OK')"
```

#### 2. Token Expired
```bash
# Manually refresh tokens
docker exec -it litellm-litellm-1 litellm claude refresh

# Or re-authenticate
docker exec -it litellm-litellm-1 litellm claude login
```

#### 3. API Calls Fail
```bash
# Check if authenticated
curl http://localhost:4000/auth/claude/oauth/status

# Check token file exists
docker exec litellm-litellm-1 cat /app/.litellm/claude_tokens.json

# Check environment variables
docker exec litellm-litellm-1 env | grep CLAUDE
```

#### 4. Database Issues
```bash
# Check database tables
docker exec litellm-db-1 psql -U llmproxy -d litellm -c "\dt"

# Check OAuth tokens table
docker exec litellm-db-1 psql -U llmproxy -d litellm -c "SELECT * FROM \"LiteLLM_ClaudeOAuthTokens\";"

# Reset database
docker-compose -f docker-compose.test-oauth.yml down -v
docker-compose -f docker-compose.test-oauth.yml up -d
```

### Debug Mode

Enable debug mode for more detailed logs:

1. **Set environment variables:**
```bash
export LITELLM_LOG_LEVEL=DEBUG
export DETAILED_DEBUG=true
```

2. **Restart containers:**
```bash
docker-compose -f docker-compose.test-oauth.yml restart litellm
```

3. **View detailed logs:**
```bash
docker logs litellm-litellm-1 -f 2>&1 | grep -E "OAuth|Token|Claude"
```

### Using Debug Tools

Start with debug profile to access database and Redis tools:
```bash
docker-compose -f docker-compose.test-oauth.yml --profile debug up -d

# Access Adminer (database UI)
open http://localhost:8080
# Server: db, Username: llmproxy, Password: dbpassword9090, Database: litellm

# Access Redis Commander
open http://localhost:8081
```

## Advanced Testing

### 1. Test Token Refresh

```python
# test_token_refresh.py
import time
import subprocess

# Set token to expire soon
subprocess.run([
    "docker", "exec", "litellm-litellm-1",
    "python", "-c",
    """
import json
import time
token_file = '/app/.litellm/claude_tokens.json'
with open(token_file, 'r') as f:
    tokens = json.load(f)
tokens['expiresAt'] = int(time.time()) + 60  # Expire in 1 minute
with open(token_file, 'w') as f:
    json.dump(tokens, f)
print('Token set to expire in 60 seconds')
"""
])

# Wait for expiration
print("Waiting for token to expire...")
time.sleep(65)

# Make API call (should auto-refresh)
subprocess.run([
    "curl", "-X", "POST", "http://localhost:4000/v1/chat/completions",
    "-H", "Authorization: Bearer sk-oauth-test-1234",
    "-H", "Content-Type: application/json",
    "-d", '{"model": "claude-haiku", "messages": [{"role": "user", "content": "test"}]}'
])
```

### 2. Load Testing

```bash
# Install hey (HTTP load generator)
brew install hey  # macOS
# or
sudo apt-get install hey  # Ubuntu

# Run load test
hey -n 100 -c 10 \
  -H "Authorization: Bearer sk-oauth-test-1234" \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-haiku", "messages": [{"role": "user", "content": "Hi"}]}' \
  http://localhost:4000/v1/chat/completions
```

### 3. Multi-User Testing

```bash
# Create multiple OAuth sessions
for i in {1..3}; do
  docker exec -it litellm-litellm-1 bash -c "
    export USER_ID=user_$i
    litellm claude login
    # Complete authentication for each user
  "
done
```

## Cleanup

### Stop and Remove Containers
```bash
# Stop containers
docker-compose -f docker-compose.test-oauth.yml down

# Remove containers and volumes
docker-compose -f docker-compose.test-oauth.yml down -v

# Remove OAuth tokens
docker volume rm litellm_oauth_tokens
```

### Reset OAuth State
```bash
# Clear all OAuth tokens
docker exec -it litellm-litellm-1 litellm claude logout

# Remove token files
docker exec litellm-litellm-1 rm -rf /app/.litellm/*
```

## Security Considerations

### Production Deployment

1. **Change default credentials:**
   - Generate secure master key
   - Use strong database password
   - Set unique encryption key

2. **Use HTTPS:**
   - Deploy behind reverse proxy (nginx/traefik)
   - Enable SSL/TLS certificates

3. **Secure token storage:**
   - Use encrypted database storage
   - Implement key rotation
   - Set appropriate file permissions

4. **Network isolation:**
   - Use private networks
   - Restrict port exposure
   - Implement firewall rules

## Useful Commands Reference

```bash
# Container management
docker-compose -f docker-compose.test-oauth.yml ps         # List containers
docker-compose -f docker-compose.test-oauth.yml logs -f    # View logs
docker-compose -f docker-compose.test-oauth.yml restart    # Restart services
docker-compose -f docker-compose.test-oauth.yml down       # Stop services

# OAuth CLI commands
docker exec -it litellm-litellm-1 litellm claude login     # Start OAuth
docker exec -it litellm-litellm-1 litellm claude status    # Check status
docker exec -it litellm-litellm-1 litellm claude refresh   # Refresh tokens
docker exec -it litellm-litellm-1 litellm claude logout    # Clear tokens
docker exec -it litellm-litellm-1 litellm claude export    # Export tokens

# Debugging
docker exec -it litellm-litellm-1 bash                     # Enter container
docker logs litellm-litellm-1 --tail 100                   # View recent logs
docker inspect litellm-litellm-1                           # Inspect container

# Database access
docker exec litellm-db-1 psql -U llmproxy -d litellm       # Access database
docker exec litellm-redis-1 redis-cli                      # Access Redis
```

## Support

For issues or questions:
- Check the [OAuth documentation](docs/claude_oauth.md)
- Review container logs: `docker logs litellm-litellm-1`
- File an issue on GitHub with logs and error messages