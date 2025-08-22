# Claude OAuth Authentication

LiteLLM supports OAuth authentication for Claude AI, enabling secure access to Claude's API through the OAuth 2.0 + PKCE flow.

## Overview

The Claude OAuth implementation provides:
- **OAuth 2.0 + PKCE Flow**: Secure initial authentication with Claude
- **Token Management**: Automatic refresh of expired tokens  
- **Database Storage**: Encrypted token storage in PostgreSQL with automatic fallback
- **Multi-User Support**: Per-user token management for production deployments
- **Storage Hierarchy**: Database → Cache → File → Environment variable fallback
- **CLI Integration**: Simple command-line authentication flow
- **API Integration**: Web endpoints for OAuth flow in server deployments
- **Docker Support**: Full containerized deployment with persistent storage

## Quick Start

### 1. Initial Authentication

Run the CLI command to start the OAuth flow:

```bash
litellm claude login
```

This will:
1. Generate an authorization URL
2. Open your browser to Claude's OAuth page
3. After authorization, you'll be redirected to the Claude Console
4. Copy the authorization code from the redirect URL
5. Complete authentication:

```bash
litellm claude callback <CODE>
```

### 2. Check Token Status

```bash
litellm claude status
```

### 3. Refresh Tokens

Tokens are automatically refreshed, but you can manually refresh:

```bash
litellm claude refresh
```

### 4. Logout

```bash
litellm claude logout
```

## Configuration

### Environment Variables

Set these after authentication for automatic token loading:

```bash
export CLAUDE_ACCESS_TOKEN="your_access_token"
export CLAUDE_REFRESH_TOKEN="your_refresh_token"
export CLAUDE_EXPIRES_AT="expiration_timestamp"
export CLAUDE_TOKEN_ENCRYPTION_KEY="your-32-byte-encryption-key"  # Optional, for token encryption
```

### Proxy Configuration

Add to your `config.yaml`:

```yaml
model_list:
  - model_name: claude-3-opus
    litellm_params:
      model: claude-3-opus-20240229
      api_key: "oauth"  # Use "oauth" to indicate OAuth authentication

# General settings (for database storage)
general_settings:
  database_url: "${DATABASE_URL}"  # PostgreSQL connection string
  master_key: "${LITELLM_MASTER_KEY}"

# OAuth configuration (optional - for advanced settings)
claude_oauth:
  enabled: true
  token_file: "~/.litellm/claude_tokens.json"  # Fallback file storage
  encryption_key: "${CLAUDE_TOKEN_ENCRYPTION_KEY}"
  auto_refresh: true
  refresh_buffer: 300  # Refresh 5 minutes before expiration
  use_database: true  # Enable database storage when available
```

### Database Configuration

For production deployments with database storage:

```yaml
# PostgreSQL connection for token storage
general_settings:
  database_url: "postgresql://user:password@host:5432/litellm"
  
# This enables the LiteLLM_ClaudeOAuthTokens table for secure token storage
# Tokens are encrypted before storage and linked to user accounts
```

## API Endpoints

When running the proxy server, OAuth endpoints are available:

### Start OAuth Flow
```http
GET /auth/claude/oauth/start
```

Returns:
```json
{
  "authorization_url": "https://claude.ai/oauth/authorize?...",
  "state": "random_state_parameter"
}
```

### Complete OAuth Flow
```http
POST /auth/claude/oauth/exchange
Content-Type: application/json

{
  "code": "authorization_code_from_callback",
  "state": "state_from_start"
}
```

Returns:
```json
{
  "success": true,
  "expires_in": 3600
}
```

### Check Token Status
```http
GET /auth/claude/oauth/status
```

Returns:
```json
{
  "authenticated": true,
  "expires_in": 3542,
  "needs_refresh": false
}
```

## Python SDK Usage

### Using the Auth Service

```python
from litellm.proxy.auth.claude_auth_service import get_auth_service

# Get auth service instance
auth_service = get_auth_service()

# Get access token (auto-refreshes if needed)
token = await auth_service.get_access_token()

# Check if authenticated
is_authenticated = await auth_service.ensure_authenticated()

# Get headers for API requests
headers = auth_service.get_headers()
```

### Direct OAuth Flow

```python
from litellm.proxy.auth.claude_oauth_flow import ClaudeOAuthFlow

# Initialize OAuth flow
oauth_flow = ClaudeOAuthFlow()

# Start OAuth flow
auth_url, state = await oauth_flow.start_flow()
print(f"Visit: {auth_url}")

# After user authorizes, exchange code for tokens
token_data = await oauth_flow.complete_flow(code, state)
print(f"Access token: {token_data['accessToken']}")
```

### Token Management

```python
from litellm.proxy.auth.claude_oauth_handler import ClaudeOAuthHandler

# Initialize with existing tokens
handler = ClaudeOAuthHandler(
    access_token="existing_access_token",
    refresh_token="existing_refresh_token",
    expires_at=1234567890
)

# Check if token needs refresh
if handler.is_token_expired():
    token_data = await handler.refresh_access_token()

# Get valid token (auto-refreshes)
token = await handler.get_valid_token(auto_refresh=True)
```

## Token Storage

LiteLLM uses a hierarchical storage system for OAuth tokens, providing flexibility and security:

### Storage Hierarchy

```
1. Database (Primary - Production)
   ↓ PostgreSQL with encryption
   ↓ Per-user isolation
   ↓ Audit trail
   
2. Cache (Performance - Redis/Memory)
   ↓ Fast access
   ↓ TTL-based expiration
   
3. File (Fallback - CLI/Development)
   ↓ ~/.litellm/claude_tokens.json
   ↓ 0600 permissions
   
4. Environment (Legacy - Compatibility)
   ↓ CLAUDE_ACCESS_TOKEN
   ↓ CLAUDE_REFRESH_TOKEN
```

### Database Storage

When database is configured, tokens are:
- Encrypted using AES-256 (Fernet)
- Stored in `LiteLLM_ClaudeOAuthTokens` table
- Linked to user accounts
- Tracked with audit fields (created_at, updated_at, last_used)
- Refresh count tracked for monitoring

### File Storage

Used by CLI and development:
- Location: `~/.litellm/claude_tokens.json`
- Permissions: 0600 (owner read/write only)
- Format: JSON with accessToken, refreshToken, expiresAt

## Database Migration

### Running the Migration

To enable database storage, run the OAuth tokens table migration:

```sql
-- File: litellm/proxy/migrations/add_claude_oauth_tokens.sql
CREATE TABLE IF NOT EXISTS "LiteLLM_ClaudeOAuthTokens" (
    token_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(256) NOT NULL UNIQUE,
    access_token_encrypted TEXT NOT NULL,
    refresh_token_encrypted TEXT,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    scopes TEXT[] DEFAULT ARRAY[]::TEXT[],
    last_used TIMESTAMP WITH TIME ZONE,
    refresh_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(256) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(256) NOT NULL,
    CONSTRAINT fk_user_id FOREIGN KEY (user_id) 
        REFERENCES "LiteLLM_UserTable"(user_id) ON DELETE CASCADE
);
```

### Docker Migration

For Docker deployments, add the migration to your initialization:

```yaml
services:
  db:
    image: postgres:16
    volumes:
      - ./litellm/proxy/migrations/add_claude_oauth_tokens.sql:/docker-entrypoint-initdb.d/01-oauth.sql
```

### Manual Migration

```bash
# Run migration manually
psql -U your_user -d litellm -f add_claude_oauth_tokens.sql

# Verify table creation
psql -U your_user -d litellm -c "\dt LiteLLM_ClaudeOAuthTokens"
```

## Security Considerations

### Token Storage Security

Tokens are secured through multiple layers:
- **Database Encryption**: AES-256 encryption before storage
- **File Permissions**: 0600 for file-based storage
- **Memory Protection**: Sensitive data cleared after use
- **Audit Trail**: All token operations logged with timestamps

### PKCE Protection

The OAuth flow uses PKCE (Proof Key for Code Exchange) to prevent authorization code interception attacks:
- Generates cryptographically secure code verifier
- Creates SHA256 challenge for authorization request
- Verifies code exchange with original verifier

### State Management

CSRF protection through state parameter:
- Random 32-byte state generated for each flow
- State files expire after 10 minutes
- Automatic cleanup of expired states

## Troubleshooting

### Common Issues

#### Token Expired

If tokens are expired and refresh fails:
```bash
# CLI authentication
litellm claude login

# Or in Docker
docker exec -it container-name python -m litellm.proxy.auth.claude_oauth_cli login
```

#### Database Connection Issues

**Prisma Error P1012**: DATABASE_URL validation failed
```bash
# Ensure DATABASE_URL is properly formatted
export DATABASE_URL="postgresql://user:password@host:5432/database"

# For Docker, check container connectivity
docker exec container-name pg_isready -h db -U llmproxy
```

**Migration Not Run**: Table LiteLLM_ClaudeOAuthTokens doesn't exist
```bash
# Run migration manually
psql -U llmproxy -d litellm -f add_claude_oauth_tokens.sql

# Or in Docker
docker exec db-container psql -U llmproxy -d litellm -f /docker-entrypoint-initdb.d/01-oauth.sql
```

#### Invalid State Error

If you see "Invalid or expired OAuth state":
- The OAuth session has expired (10-minute timeout)
- Start a new login flow
- Check that state files aren't corrupted in `/tmp/oauth_state_*`

#### Permission Denied

File permission errors:
```bash
# Fix file permissions
chmod 600 ~/.litellm/claude_tokens.json

# In Docker, ensure volume permissions
docker exec container-name chmod 600 /app/.litellm/claude_tokens.json
```

#### Token Storage Not Working

Database storage not being used:
```python
# Verify Prisma client is initialized
handler = ClaudeOAuthHandler(
    prisma_client=prisma_client,  # Must be provided
    encryption_key=encryption_key
)

# Check if database handler is created
if handler.db_handler:
    print("Database storage enabled")
else:
    print("Falling back to file storage")
```

#### Encryption Key Issues

Invalid or missing encryption key:
```bash
# Generate proper encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Set in environment
export CLAUDE_TOKEN_ENCRYPTION_KEY="your-generated-key"
```

### Clear All Tokens

To completely reset authentication:

**CLI/File Storage:**
```bash
litellm claude logout
rm -rf ~/.litellm/claude_*
```

**Database Storage:**
```sql
-- Clear specific user's tokens
DELETE FROM "LiteLLM_ClaudeOAuthTokens" WHERE user_id = 'user_123';

-- Clear all OAuth tokens
TRUNCATE TABLE "LiteLLM_ClaudeOAuthTokens";

-- Reset user OAuth status
UPDATE "LiteLLM_UserTable" 
SET claude_oauth_enabled = FALSE, 
    claude_oauth_connected_at = NULL;
```

**Docker Reset:**
```bash
# Stop containers and remove volumes
docker-compose down -v

# Rebuild and start fresh
docker-compose up -d --build
```

### Debugging

Enable detailed logging:
```python
# Set logging level
import logging
logging.basicConfig(level=logging.DEBUG)

# Or via environment
export LITELLM_LOG_LEVEL=DEBUG
export DETAILED_DEBUG=true
```

Check token status in database:
```sql
-- View all token records
SELECT 
    token_id,
    user_id,
    expires_at,
    last_used,
    refresh_count,
    created_at,
    updated_at
FROM "LiteLLM_ClaudeOAuthTokens";

-- Check specific user
SELECT * FROM "LiteLLM_ClaudeOAuthTokens" 
WHERE user_id = 'your_user_id';
```

Monitor token refresh:
```bash
# Watch logs for refresh activity
docker logs -f container-name | grep -i "refresh\|token\|oauth"
```

## OAuth Flow Details

### Authorization Request

The OAuth flow starts with an authorization request to Claude:

```
https://claude.ai/oauth/authorize?
  client_id=9d1c250a-e61b-44d9-88ed-5944d1962f5e
  &response_type=code
  &redirect_uri=https://console.anthropic.com/oauth/code/callback
  &scope=org:create_api_key user:profile user:inference
  &code_challenge=<PKCE_CHALLENGE>
  &code_challenge_method=S256
  &state=<CSRF_STATE>
  &code=true
```

### Token Exchange

After authorization, exchange the code for tokens:

```http
POST https://console.anthropic.com/v1/oauth/token
Content-Type: application/json

{
  "grant_type": "authorization_code",
  "client_id": "9d1c250a-e61b-44d9-88ed-5944d1962f5e",
  "code": "<AUTHORIZATION_CODE>",
  "redirect_uri": "https://console.anthropic.com/oauth/code/callback",
  "code_verifier": "<PKCE_VERIFIER>",
  "state": "<CSRF_STATE>"
}
```

### Token Refresh

Refresh expired tokens:

```http
POST https://api.anthropic.com/v1/oauth/refresh
Content-Type: application/json
anthropic-beta: oauth-2025-04-20

{
  "refresh_token": "<REFRESH_TOKEN>"
}
```

## Multi-User Support

LiteLLM's OAuth implementation fully supports multi-user environments with database storage:

### Per-User Token Management

Each user has isolated OAuth tokens:

```python
from litellm.proxy.auth.claude_oauth_handler import ClaudeOAuthHandler

# Initialize handler with database
handler = ClaudeOAuthHandler(
    prisma_client=prisma_client,
    encryption_key=encryption_key
)

# Store tokens for specific user
await handler.store_tokens(
    user_id="user_123",
    token_data={
        "accessToken": "user_specific_token",
        "refreshToken": "user_specific_refresh",
        "expiresAt": 1234567890
    }
)

# Retrieve tokens for specific user
token = await handler.get_valid_token(
    user_id="user_123",
    auto_refresh=True
)
```

### Database Schema

User tokens are stored with complete isolation:

```sql
-- Each user has one OAuth token record
-- user_id is UNIQUE, ensuring one token set per user
-- Cascade delete removes tokens when user is deleted
```

### API Usage with User Context

```python
# In your API endpoint
@app.post("/chat/completions")
async def chat_completion(request: Request, user_id: str):
    # Get user-specific token
    auth_service = get_auth_service()
    token = await auth_service.get_access_token(user_id=user_id)
    
    if not token:
        raise HTTPException(401, "User not authenticated with Claude")
    
    # Use token for API call
    response = await litellm.acompletion(
        model="claude-3-opus",
        messages=request.messages,
        api_key=token  # User-specific OAuth token
    )
    return response
```

### User Token Status

Check OAuth status for all users:

```sql
-- View OAuth status for all users
SELECT 
    u.user_id,
    u.user_email,
    t.expires_at,
    t.last_used,
    t.refresh_count,
    CASE 
        WHEN t.expires_at > NOW() THEN 'active'
        WHEN t.refresh_token_encrypted IS NOT NULL THEN 'expired_refreshable'
        ELSE 'expired'
    END AS status
FROM LiteLLM_UserTable u
LEFT JOIN LiteLLM_ClaudeOAuthTokens t ON u.user_id = t.user_id
WHERE u.claude_oauth_enabled = TRUE;
```

## Docker Deployment

### Complete Docker Setup

1. **Docker Compose Configuration**

```yaml
# docker-compose.yml
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
      - oauth_tokens:/app/.litellm  # Persistent token storage
    depends_on:
      db:
        condition: service_healthy

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

volumes:
  postgres_data:
  oauth_tokens:
```

2. **OAuth Flow in Docker**

```bash
# Start containers
docker-compose up -d

# Run OAuth login inside container
docker exec -it litellm-container python -m litellm.proxy.auth.claude_oauth_cli login

# Complete authentication
docker exec -it litellm-container python -m litellm.proxy.auth.claude_oauth_cli callback <CODE>

# Check status
docker exec -it litellm-container python -m litellm.proxy.auth.claude_oauth_cli status
```

3. **Environment Variables**

Create `.env` file:

```env
# Database
DATABASE_URL=postgresql://llmproxy:dbpassword@db:5432/litellm

# OAuth
CLAUDE_TOKEN_ENCRYPTION_KEY=your-32-byte-encryption-key-here
LITELLM_MASTER_KEY=sk-your-master-key

# Optional: Pre-configured tokens (for migration)
CLAUDE_ACCESS_TOKEN=
CLAUDE_REFRESH_TOKEN=
CLAUDE_EXPIRES_AT=
```

### Persistent Storage

Tokens persist across container restarts:
- Database storage for production
- Volume mount for file-based storage
- Automatic migration on container start

## Advanced Configuration

### Custom Token Storage

Implement custom token storage:

```python
from litellm.proxy.auth.claude_auth_service import ClaudeAuthService

class CustomAuthService(ClaudeAuthService):
    def _save_tokens(self, token_data):
        # Custom storage logic
        my_storage.save(token_data)
    
    def _load_tokens(self):
        # Custom loading logic
        return my_storage.load()
```

### Database Handler Usage

Direct database operations:

```python
from litellm.proxy.auth.claude_oauth_db import ClaudeOAuthDatabase

# Initialize database handler
db = ClaudeOAuthDatabase(prisma_client, encryption_key)

# Store tokens
await db.store_tokens(
    user_id="user_123",
    access_token="token",
    refresh_token="refresh",
    expires_at=timestamp,
    scopes=["org:create_api_key"],
    created_by="admin"
)

# Get tokens
tokens = await db.get_tokens("user_123")

# Find expiring tokens
expiring_users = await db.get_expiring_tokens(minutes=10)

# Update after refresh
await db.update_token_expiry(
    user_id="user_123",
    new_access_token="new_token",
    new_expires_at=new_timestamp
)
```

### Programmatic OAuth Flow

For server deployments without browser access:

```python
# Start flow programmatically
auth_url, state = await oauth_flow.start_flow()

# Display URL to user
print(f"Visit this URL: {auth_url}")

# User provides code manually
code = input("Enter authorization code: ")

# Complete flow
tokens = await oauth_flow.complete_flow(code, state)
```

## Migration Guide

### From API Keys to OAuth

1. Obtain OAuth tokens:
   ```bash
   litellm claude login
   ```

2. Update your configuration:
   ```yaml
   # Before
   api_key: "sk-ant-..."
   
   # After
   api_key: "oauth"
   ```

3. Ensure tokens are available via environment or file

### From Manual Tokens to Auth Service

```python
# Before
access_token = os.getenv("CLAUDE_ACCESS_TOKEN")
headers = {"Authorization": f"Bearer {access_token}"}

# After
from litellm.proxy.auth.claude_auth_service import quick_authenticate
token = await quick_authenticate()
```

## Support

For issues or questions:
- GitHub Issues: [litellm/litellm](https://github.com/BerriAI/litellm/issues)
- Documentation: [docs.litellm.ai](https://docs.litellm.ai)