#!/bin/bash

# Claude OAuth Docker Testing Script
# This script automates the testing of Claude OAuth implementation with Docker

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.test-oauth.yml}"
ENV_FILE="${ENV_FILE:-.env.oauth}"
CONFIG_FILE="${CONFIG_FILE:-config.oauth.yaml}"
CONTAINER_NAME="litellm-litellm-1"
API_BASE="http://localhost:4000"
MASTER_KEY="${LITELLM_MASTER_KEY:-sk-oauth-test-1234}"

# Functions
print_header() {
    echo -e "\n${BLUE}============================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Check prerequisites
check_prerequisites() {
    print_header "Checking Prerequisites"
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        exit 1
    fi
    print_success "Docker is installed"
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        print_error "Docker Compose is not installed"
        exit 1
    fi
    print_success "Docker Compose is installed"
    
    # Check if configuration files exist
    if [ ! -f "$CONFIG_FILE" ]; then
        print_error "Configuration file $CONFIG_FILE not found"
        exit 1
    fi
    print_success "Configuration file found: $CONFIG_FILE"
    
    if [ ! -f "$ENV_FILE" ]; then
        print_error "Environment file $ENV_FILE not found"
        exit 1
    fi
    print_success "Environment file found: $ENV_FILE"
}

# Build and start containers
start_containers() {
    print_header "Starting Docker Containers"
    
    # Check if using docker-compose or docker compose
    if command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
    else
        COMPOSE_CMD="docker compose"
    fi
    
    # Stop any existing containers
    print_info "Stopping existing containers..."
    $COMPOSE_CMD -f $COMPOSE_FILE down 2>/dev/null || true
    
    # Build and start containers
    print_info "Building and starting containers..."
    $COMPOSE_CMD -f $COMPOSE_FILE --env-file $ENV_FILE up -d --build
    
    # Wait for services to be ready
    print_info "Waiting for services to be ready..."
    sleep 10
    
    # Check container status
    if docker ps | grep -q $CONTAINER_NAME; then
        print_success "Containers are running"
    else
        print_error "Containers failed to start"
        docker logs $CONTAINER_NAME 2>/dev/null || true
        exit 1
    fi
}

# Health check
check_health() {
    print_header "Health Check"
    
    # Check LiteLLM health endpoint
    print_info "Checking LiteLLM health..."
    if curl -s -f "$API_BASE/health" > /dev/null 2>&1; then
        print_success "LiteLLM is healthy"
        
        # Get detailed health info
        HEALTH_INFO=$(curl -s "$API_BASE/health/liveliness" 2>/dev/null || echo "{}")
        echo "Health info: $HEALTH_INFO"
    else
        print_error "LiteLLM health check failed"
        docker logs $CONTAINER_NAME --tail 50
        exit 1
    fi
    
    # Check database connection
    print_info "Checking database connection..."
    if docker exec litellm-db-1 pg_isready -U llmproxy -d litellm > /dev/null 2>&1; then
        print_success "Database is ready"
    else
        print_warning "Database might not be ready"
    fi
}

# Test OAuth endpoints
test_oauth_endpoints() {
    print_header "Testing OAuth Endpoints"
    
    # Test OAuth status endpoint
    print_info "Testing OAuth status endpoint..."
    STATUS_RESPONSE=$(curl -s "$API_BASE/auth/claude/oauth/status" 2>/dev/null || echo "{}")
    
    if echo "$STATUS_RESPONSE" | grep -q "authenticated"; then
        IS_AUTHENTICATED=$(echo "$STATUS_RESPONSE" | grep -o '"authenticated":[^,}]*' | cut -d: -f2)
        if [ "$IS_AUTHENTICATED" = "true" ]; then
            print_success "Already authenticated with OAuth"
        else
            print_warning "Not authenticated yet"
        fi
        echo "OAuth status: $STATUS_RESPONSE"
    else
        print_warning "OAuth status endpoint not available"
    fi
    
    # Test OAuth start endpoint
    print_info "Testing OAuth start endpoint..."
    START_RESPONSE=$(curl -s "$API_BASE/auth/claude/oauth/start" 2>/dev/null || echo "{}")
    
    if echo "$START_RESPONSE" | grep -q "authorization_url"; then
        print_success "OAuth start endpoint is working"
        AUTH_URL=$(echo "$START_RESPONSE" | grep -o '"authorization_url":"[^"]*' | cut -d'"' -f4)
        STATE=$(echo "$START_RESPONSE" | grep -o '"state":"[^"]*' | cut -d'"' -f4)
        
        echo -e "\n${YELLOW}Authorization URL:${NC}"
        echo "$AUTH_URL"
        echo -e "\n${YELLOW}State:${NC} $STATE"
    else
        print_warning "OAuth start endpoint returned unexpected response"
        echo "Response: $START_RESPONSE"
    fi
}

# Test model endpoints
test_model_endpoints() {
    print_header "Testing Model Endpoints"
    
    # List available models
    print_info "Listing available models..."
    MODELS_RESPONSE=$(curl -s -H "Authorization: Bearer $MASTER_KEY" "$API_BASE/v1/models" 2>/dev/null || echo "{}")
    
    if echo "$MODELS_RESPONSE" | grep -q "data"; then
        print_success "Models endpoint is working"
        
        # Count models
        MODEL_COUNT=$(echo "$MODELS_RESPONSE" | grep -o '"id"' | wc -l)
        echo "Found $MODEL_COUNT models configured"
        
        # List model names
        echo -e "\nConfigured models:"
        echo "$MODELS_RESPONSE" | grep -o '"id":"[^"]*' | cut -d'"' -f4 | while read model; do
            echo "  - $model"
        done
    else
        print_error "Failed to list models"
        echo "Response: $MODELS_RESPONSE"
    fi
}

# Interactive OAuth login
interactive_oauth_login() {
    print_header "Interactive OAuth Login"
    
    echo -e "${YELLOW}To complete OAuth authentication:${NC}"
    echo "1. Run the following command in a new terminal:"
    echo -e "   ${GREEN}docker exec -it $CONTAINER_NAME litellm claude login${NC}"
    echo ""
    echo "2. Open the authorization URL in your browser"
    echo "3. Complete the authentication flow"
    echo "4. Copy the authorization code"
    echo ""
    echo "5. Run the callback command with your code:"
    echo -e "   ${GREEN}docker exec -it $CONTAINER_NAME litellm claude callback <CODE>${NC}"
    echo ""
    echo "6. Check the token status:"
    echo -e "   ${GREEN}docker exec -it $CONTAINER_NAME litellm claude status${NC}"
    echo ""
    
    read -p "Press Enter after completing OAuth authentication..."
}

# Test authenticated API call
test_api_call() {
    print_header "Testing Authenticated API Call"
    
    # Check if authenticated first
    STATUS_RESPONSE=$(curl -s "$API_BASE/auth/claude/oauth/status" 2>/dev/null || echo "{}")
    IS_AUTHENTICATED=$(echo "$STATUS_RESPONSE" | grep -o '"authenticated":[^,}]*' | cut -d: -f2)
    
    if [ "$IS_AUTHENTICATED" != "true" ]; then
        print_warning "Not authenticated. Skipping API call test."
        return
    fi
    
    print_info "Testing chat completion with Claude Haiku..."
    
    # Make a simple chat completion request
    CHAT_RESPONSE=$(curl -s -X POST "$API_BASE/v1/chat/completions" \
        -H "Authorization: Bearer $MASTER_KEY" \
        -H "Content-Type: application/json" \
        -d '{
            "model": "claude-haiku",
            "messages": [{"role": "user", "content": "Say hello in 5 words or less"}],
            "max_tokens": 20
        }' 2>/dev/null || echo "{}")
    
    if echo "$CHAT_RESPONSE" | grep -q "choices"; then
        print_success "Chat completion successful!"
        
        # Extract and display the response
        CONTENT=$(echo "$CHAT_RESPONSE" | grep -o '"content":"[^"]*' | head -1 | cut -d'"' -f4)
        echo "Model response: $CONTENT"
    else
        print_error "Chat completion failed"
        echo "Response: $CHAT_RESPONSE"
        
        # Check logs for errors
        echo -e "\n${YELLOW}Container logs:${NC}"
        docker logs $CONTAINER_NAME --tail 20
    fi
}

# Show logs
show_logs() {
    print_header "Container Logs"
    
    echo "Showing last 50 lines of logs..."
    docker logs $CONTAINER_NAME --tail 50
}

# Cleanup
cleanup() {
    print_header "Cleanup"
    
    read -p "Do you want to stop and remove containers? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if command -v docker-compose &> /dev/null; then
            docker-compose -f $COMPOSE_FILE down
        else
            docker compose -f $COMPOSE_FILE down
        fi
        print_success "Containers stopped and removed"
    else
        print_info "Containers are still running"
        echo "To stop them later, run: docker-compose -f $COMPOSE_FILE down"
    fi
}

# Main execution
main() {
    print_header "Claude OAuth Docker Testing"
    
    # Run tests
    check_prerequisites
    start_containers
    check_health
    test_oauth_endpoints
    test_model_endpoints
    
    # Ask if user wants to do interactive login
    read -p "Do you want to perform interactive OAuth login? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        interactive_oauth_login
        test_api_call
    fi
    
    # Show logs option
    read -p "Do you want to see container logs? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        show_logs
    fi
    
    # Cleanup
    cleanup
    
    print_header "Testing Complete"
    print_success "All tests finished!"
    
    echo -e "\n${GREEN}Useful commands:${NC}"
    echo "  View logs: docker logs $CONTAINER_NAME -f"
    echo "  Enter container: docker exec -it $CONTAINER_NAME bash"
    echo "  OAuth login: docker exec -it $CONTAINER_NAME litellm claude login"
    echo "  Check status: docker exec -it $CONTAINER_NAME litellm claude status"
    echo "  Stop containers: docker-compose -f $COMPOSE_FILE down"
}

# Handle interrupts
trap 'echo -e "\n${RED}Interrupted${NC}"; exit 1' INT TERM

# Run main function
main "$@"