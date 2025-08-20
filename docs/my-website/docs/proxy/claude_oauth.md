# Claude OAuth Authentication

Use OAuth 2.0 with PKCE to authenticate with Claude Max models through the LiteLLM Proxy. This provides secure, token-based access to Claude Sonnet 4 and Claude Opus 4.1 models.

## Features

- 🔐 **PKCE OAuth Flow**: Secure authentication using Proof Key for Code Exchange
- 🔄 **Automatic Token Refresh**: Tokens are refreshed automatically before expiration
- 🔑 **Encrypted Token Storage**: AES-256 encryption for stored tokens
- 👥 **Multi-User Support**: Isolated token management per user
- 📊 **Token Lifecycle Management**: Track token usage, expiration, and refresh counts
- 🚀 **Zero-Downtime Auth**: Transparent token refresh without request interruption

## Quick Start

### 1. Set Environment Variables

```bash
# Required
export CLAUDE_OAUTH_CLIENT_ID="your-client-id"
export CLAUDE_OAUTH_REDIRECT_URI="http://localhost:4000/auth/claude/callback"

# Optional but recommended
export CLAUDE_TOKEN_ENCRYPTION_KEY="your-encryption-key"  # Generate with: openssl rand -base64 32
export DATABASE_URL="postgresql://user:pass@localhost/litellm"  # For persistent token storage
```

### 2. Configure LiteLLM Proxy

Add to your `config.yaml`:

```yaml
model_list:
  - model_name: claude-3-sonnet
    litellm_params:
      model: anthropic/claude-3-sonnet-4-20250514
      
  - model_name: claude-3-opus
    litellm_params:
      model: anthropic/claude-3-opus-4-20250805

general_settings:
  master_key: sk-1234
  enable_claude_oauth: true
  
  claude_oauth:
    enabled: true
    client_id: "${CLAUDE_OAUTH_CLIENT_ID}"
    redirect_uri: "${CLAUDE_OAUTH_REDIRECT_URI}"
    scopes: ["claude:chat", "claude:models", "claude:read"]
    
    # Token management
    token_encryption: true
    auto_refresh: true
    refresh_threshold: 300  # Refresh 5 minutes before expiry
    
    # Security settings
    pkce_required: true
    state_encryption: true
```

### 3. Start the Proxy

```bash
litellm --config config.yaml
```

### 4. Authenticate a User

Users need to authenticate once to connect their Claude account:

```bash
# Navigate to the authorization URL
curl http://localhost:4000/auth/claude/authorize \
  -H "Authorization: Bearer YOUR_LITELLM_KEY"
```

This will redirect to Claude's OAuth page. After authorization, tokens are stored securely.

## API Endpoints

### Authorization Flow

#### `GET /auth/claude/authorize`
Initiate OAuth flow for the authenticated user.

```bash
curl http://localhost:4000/auth/claude/authorize \
  -H "Authorization: Bearer YOUR_LITELLM_KEY"
```

**Query Parameters:**
- `scopes` (optional): Space-separated OAuth scopes
- `redirect_uri` (optional): Custom redirect URI

#### `GET /auth/claude/callback`
OAuth callback endpoint (handled automatically).

**Query Parameters:**
- `code`: Authorization code from Claude
- `state`: CSRF protection state

### Token Management

#### `POST /auth/claude/refresh`
Manually refresh the OAuth token.

```bash
curl -X POST http://localhost:4000/auth/claude/refresh \
  -H "Authorization: Bearer YOUR_LITELLM_KEY"
```

#### `GET /auth/claude/status`
Check OAuth connection status.

```bash
curl http://localhost:4000/auth/claude/status \
  -H "Authorization: Bearer YOUR_LITELLM_KEY"
```

**Response:**
```json
{
  "authenticated": true,
  "user_id": "user-123",
  "expires_in": 3542,
  "expires_at": "2024-01-20T15:30:00Z",
  "scopes": ["claude:chat", "claude:models"],
  "refresh_count": 2,
  "auto_refresh_enabled": true
}
```

#### `DELETE /auth/claude/revoke`
Revoke OAuth tokens and disconnect Claude account.

```bash
curl -X DELETE http://localhost:4000/auth/claude/revoke \
  -H "Authorization: Bearer YOUR_LITELLM_KEY"
```

#### `GET /auth/claude/health`
Health check for OAuth service.

```bash
curl http://localhost:4000/auth/claude/health
```

## Using Claude Models

Once authenticated, use Claude models like any other LiteLLM model:

```python
from litellm import completion

# OAuth token is automatically injected
response = completion(
    model="claude-3-sonnet",
    messages=[{"role": "user", "content": "Hello!"}],
    api_key="YOUR_LITELLM_KEY"  # Your LiteLLM proxy key
)
```

### With OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_LITELLM_KEY",
    base_url="http://localhost:4000"
)

response = client.chat.completions.create(
    model="claude-3-opus",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

### With cURL

```bash
curl -X POST http://localhost:4000/chat/completions \
  -H "Authorization: Bearer YOUR_LITELLM_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-sonnet",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## Advanced Configuration

### Database Setup

For production, use PostgreSQL for persistent token storage:

1. Run the migration:
```bash
psql $DATABASE_URL < litellm/proxy/migrations/add_claude_oauth_tokens.sql
```

2. Update Prisma schema:
```bash
npx prisma generate
npx prisma migrate deploy
```

### Security Best Practices

1. **Generate Strong Encryption Key**:
```bash
export CLAUDE_TOKEN_ENCRYPTION_KEY=$(openssl rand -base64 32)
```

2. **Use HTTPS in Production**:
```yaml
claude_oauth:
  redirect_uri: "https://your-domain.com/auth/claude/callback"
```

3. **Enable Rate Limiting**:
```yaml
claude_oauth:
  rate_limit:
    authorize: 10/hour
    refresh: 100/hour
```

4. **Audit Logging**:
```yaml
claude_oauth:
  audit_log: true
  log_level: INFO
```

### Multi-User Configuration

Enable team-based OAuth:

```yaml
claude_oauth:
  multi_user:
    enabled: true
    isolation: strict  # Each user has separate tokens
    shared_models: false  # Don't share model access
```

### Token Refresh Strategy

Configure automatic refresh behavior:

```yaml
claude_oauth:
  auto_refresh:
    enabled: true
    threshold: 300  # Seconds before expiry
    max_retries: 3
    retry_backoff: exponential
    background_refresh: true  # Refresh in background
```

## Monitoring

### Token Statistics

Get OAuth token statistics:

```bash
curl http://localhost:4000/auth/claude/health
```

Response includes:
- Active tokens count
- Tokens expiring soon
- Refresh statistics
- Failed refresh attempts

### Prometheus Metrics

Available metrics:
- `litellm_claude_oauth_tokens_active`
- `litellm_claude_oauth_tokens_refreshed`
- `litellm_claude_oauth_auth_failures`
- `litellm_claude_oauth_token_expiry_seconds`

## Troubleshooting

### Common Issues

**"OAuth token expired"**
- Tokens are auto-refreshed 5 minutes before expiry
- Manually refresh: `POST /auth/claude/refresh`

**"No OAuth token found"**
- User needs to authenticate: `GET /auth/claude/authorize`

**"PKCE verifier not found"**
- State expired (10 minute timeout)
- Restart authorization flow

**"Failed to refresh token"**
- Check refresh token validity
- User may need to re-authenticate

### Debug Mode

Enable detailed logging:

```yaml
claude_oauth:
  debug: true
  log_tokens: false  # Never log actual tokens
```

```bash
litellm --config config.yaml --detailed_debug
```

## Migration from API Keys

Gradual migration path:

1. **Enable Both Auth Methods**:
```yaml
claude_oauth:
  fallback_to_api_key: true  # Use API key if no OAuth token
```

2. **Monitor Usage**:
```sql
SELECT 
  COUNT(*) as total_requests,
  SUM(CASE WHEN using_oauth THEN 1 ELSE 0 END) as oauth_requests
FROM request_logs;
```

3. **Deprecate API Keys**:
```yaml
claude_oauth:
  fallback_to_api_key: false
  require_oauth_for_claude: true
```

## API Reference

### Token Storage Schema

```sql
CREATE TABLE LiteLLM_ClaudeOAuthTokens (
  token_id UUID PRIMARY KEY,
  user_id VARCHAR(256) NOT NULL,
  access_token_encrypted TEXT NOT NULL,
  refresh_token_encrypted TEXT,
  expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
  scopes TEXT[],
  last_used TIMESTAMP WITH TIME ZONE,
  refresh_count INTEGER DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `CLAUDE_OAUTH_CLIENT_ID` | OAuth client ID | Yes | - |
| `CLAUDE_OAUTH_REDIRECT_URI` | OAuth callback URL | Yes | - |
| `CLAUDE_TOKEN_ENCRYPTION_KEY` | AES-256 encryption key | No | Auto-generated |
| `CLAUDE_OAUTH_SCOPES` | Space-separated scopes | No | `claude:chat claude:models` |
| `CLAUDE_OAUTH_AUTO_REFRESH` | Enable auto-refresh | No | `true` |
| `CLAUDE_OAUTH_REFRESH_THRESHOLD` | Seconds before expiry to refresh | No | `300` |

## Support

- [GitHub Issues](https://github.com/BerriAI/litellm/issues)
- [Discord Community](https://discord.gg/wuPM9dRgDw)
- [Enterprise Support](https://calendly.com/d/4mp-gd3-k5k/litellm-1-1-onboarding-chat)