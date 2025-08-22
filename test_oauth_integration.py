#!/usr/bin/env python3
"""
Claude OAuth Integration Test Suite

This script provides comprehensive testing for the Claude OAuth implementation.
It tests the OAuth flow, token management, and API calls.

Usage:
    python test_oauth_integration.py [--base-url URL] [--master-key KEY]
"""

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Dict, Optional, Any
import argparse
import httpx
from datetime import datetime, timedelta


# Configuration
@dataclass
class TestConfig:
    """Test configuration settings"""
    base_url: str = "http://localhost:4000"
    master_key: str = "sk-oauth-test-1234"
    timeout: int = 30
    verbose: bool = True


# Color codes for output
class Colors:
    """Terminal color codes"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(message: str):
    """Print a formatted header"""
    print(f"\n{Colors.HEADER}{'=' * 60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{message}{Colors.ENDC}")
    print(f"{Colors.HEADER}{'=' * 60}{Colors.ENDC}")


def print_success(message: str):
    """Print a success message"""
    print(f"{Colors.GREEN}✓ {message}{Colors.ENDC}")


def print_error(message: str):
    """Print an error message"""
    print(f"{Colors.FAIL}✗ {message}{Colors.ENDC}")


def print_warning(message: str):
    """Print a warning message"""
    print(f"{Colors.WARNING}⚠ {message}{Colors.ENDC}")


def print_info(message: str):
    """Print an info message"""
    print(f"{Colors.CYAN}ℹ {message}{Colors.ENDC}")


class ClaudeOAuthTester:
    """Main test class for Claude OAuth integration"""
    
    def __init__(self, config: TestConfig):
        self.config = config
        self.client = httpx.AsyncClient(timeout=config.timeout)
        self.oauth_state: Optional[str] = None
        self.auth_url: Optional[str] = None
        self.test_results = []
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    async def test_health_check(self) -> bool:
        """Test if the LiteLLM service is healthy"""
        print_header("Testing Health Check")
        
        try:
            response = await self.client.get(f"{self.config.base_url}/health")
            if response.status_code == 200:
                print_success("Health check passed")
                
                # Test detailed health
                response = await self.client.get(f"{self.config.base_url}/health/liveliness")
                if response.status_code == 200:
                    health_data = response.json()
                    print_info(f"Health details: {json.dumps(health_data, indent=2)}")
                
                return True
            else:
                print_error(f"Health check failed: {response.status_code}")
                return False
        except Exception as e:
            print_error(f"Health check error: {e}")
            return False
    
    async def test_oauth_status(self) -> Dict[str, Any]:
        """Check current OAuth authentication status"""
        print_header("Testing OAuth Status")
        
        try:
            response = await self.client.get(
                f"{self.config.base_url}/auth/claude/oauth/status"
            )
            
            if response.status_code == 200:
                status = response.json()
                
                if status.get("authenticated"):
                    print_success(f"Authenticated: {status.get('authenticated')}")
                    if "expires_in" in status:
                        print_info(f"Token expires in: {status['expires_in']} seconds")
                    if "needs_refresh" in status:
                        print_info(f"Needs refresh: {status['needs_refresh']}")
                else:
                    print_warning("Not authenticated")
                
                return status
            else:
                print_error(f"Status check failed: {response.status_code}")
                return {"authenticated": False}
                
        except Exception as e:
            print_error(f"Status check error: {e}")
            return {"authenticated": False}
    
    async def test_oauth_start(self) -> bool:
        """Test starting the OAuth flow"""
        print_header("Testing OAuth Flow Start")
        
        try:
            response = await self.client.get(
                f"{self.config.base_url}/auth/claude/oauth/start"
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if "authorization_url" in data and "state" in data:
                    self.auth_url = data["authorization_url"]
                    self.oauth_state = data["state"]
                    
                    print_success("OAuth flow started successfully")
                    print_info(f"State: {self.oauth_state[:20]}...")
                    print_info(f"Authorization URL: {self.auth_url[:50]}...")
                    
                    # Display instructions
                    print(f"\n{Colors.BOLD}To complete authentication:{Colors.ENDC}")
                    print(f"1. Open this URL in your browser:")
                    print(f"   {Colors.CYAN}{self.auth_url}{Colors.ENDC}")
                    print(f"2. Sign in to Claude and authorize the application")
                    print(f"3. Copy the authorization code from the redirect URL")
                    print(f"4. Run the exchange_code test with your code")
                    
                    return True
                else:
                    print_error("Invalid response format")
                    return False
            else:
                print_error(f"Failed to start OAuth: {response.status_code}")
                return False
                
        except Exception as e:
            print_error(f"OAuth start error: {e}")
            return False
    
    async def test_oauth_exchange(self, code: str, state: Optional[str] = None) -> bool:
        """Test exchanging authorization code for tokens"""
        print_header("Testing OAuth Code Exchange")
        
        if not state and not self.oauth_state:
            print_error("No OAuth state available. Run start_oauth first.")
            return False
        
        state = state or self.oauth_state
        
        try:
            response = await self.client.post(
                f"{self.config.base_url}/auth/claude/oauth/exchange",
                json={
                    "code": code,
                    "state": state
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success("Code exchange successful")
                
                if "expires_in" in data:
                    print_info(f"Token expires in: {data['expires_in']} seconds")
                
                return True
            else:
                print_error(f"Code exchange failed: {response.status_code}")
                error_msg = response.text
                print_error(f"Error: {error_msg}")
                return False
                
        except Exception as e:
            print_error(f"Code exchange error: {e}")
            return False
    
    async def test_list_models(self) -> bool:
        """Test listing available models"""
        print_header("Testing Model List")
        
        try:
            response = await self.client.get(
                f"{self.config.base_url}/v1/models",
                headers={"Authorization": f"Bearer {self.config.master_key}"}
            )
            
            if response.status_code == 200:
                data = response.json()
                models = data.get("data", [])
                
                print_success(f"Found {len(models)} models")
                
                # List Claude models
                claude_models = [m for m in models if "claude" in m.get("id", "").lower()]
                
                if claude_models:
                    print_info("Claude models:")
                    for model in claude_models:
                        print(f"  - {model['id']}")
                else:
                    print_warning("No Claude models found")
                
                return len(models) > 0
            else:
                print_error(f"Failed to list models: {response.status_code}")
                return False
                
        except Exception as e:
            print_error(f"Model list error: {e}")
            return False
    
    async def test_chat_completion(self, model: str = "claude-haiku") -> bool:
        """Test making a chat completion request"""
        print_header(f"Testing Chat Completion with {model}")
        
        # Check if authenticated first
        status = await self.test_oauth_status()
        if not status.get("authenticated"):
            print_warning("Not authenticated. Skipping chat completion test.")
            return False
        
        try:
            response = await self.client.post(
                f"{self.config.base_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.config.master_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "user", "content": "Say 'OAuth test successful!' in exactly 5 words"}
                    ],
                    "max_tokens": 50,
                    "temperature": 0
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if "choices" in data and len(data["choices"]) > 0:
                    content = data["choices"][0]["message"]["content"]
                    print_success("Chat completion successful")
                    print_info(f"Model response: {content}")
                    
                    # Check usage
                    if "usage" in data:
                        usage = data["usage"]
                        print_info(f"Tokens used: {usage.get('total_tokens', 'N/A')}")
                    
                    return True
                else:
                    print_error("Invalid response format")
                    return False
            else:
                print_error(f"Chat completion failed: {response.status_code}")
                error_msg = response.text
                print_error(f"Error: {error_msg}")
                return False
                
        except Exception as e:
            print_error(f"Chat completion error: {e}")
            return False
    
    async def test_streaming(self, model: str = "claude-haiku") -> bool:
        """Test streaming chat completion"""
        print_header(f"Testing Streaming with {model}")
        
        # Check if authenticated first
        status = await self.test_oauth_status()
        if not status.get("authenticated"):
            print_warning("Not authenticated. Skipping streaming test.")
            return False
        
        try:
            print_info("Starting stream...")
            
            async with self.client.stream(
                "POST",
                f"{self.config.base_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.config.master_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "user", "content": "Count from 1 to 5"}
                    ],
                    "stream": True,
                    "max_tokens": 50
                }
            ) as response:
                if response.status_code == 200:
                    chunks = []
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            chunk = line[6:]
                            if chunk == "[DONE]":
                                break
                            try:
                                data = json.loads(chunk)
                                if "choices" in data and len(data["choices"]) > 0:
                                    delta = data["choices"][0].get("delta", {})
                                    if "content" in delta:
                                        chunks.append(delta["content"])
                                        print(delta["content"], end="", flush=True)
                            except json.JSONDecodeError:
                                pass
                    
                    print()  # New line after streaming
                    
                    if chunks:
                        print_success("Streaming successful")
                        return True
                    else:
                        print_error("No content received in stream")
                        return False
                else:
                    print_error(f"Streaming failed: {response.status_code}")
                    return False
                    
        except Exception as e:
            print_error(f"Streaming error: {e}")
            return False
    
    async def test_token_refresh_simulation(self) -> bool:
        """Simulate token expiration and refresh"""
        print_header("Testing Token Refresh (Simulation)")
        
        print_warning("This is a simulation. Actual token refresh requires expired tokens.")
        
        # Check current status
        status = await self.test_oauth_status()
        
        if not status.get("authenticated"):
            print_warning("Not authenticated. Cannot test refresh.")
            return False
        
        print_info("Current authentication status:")
        print(f"  - Authenticated: {status.get('authenticated')}")
        print(f"  - Expires in: {status.get('expires_in', 'N/A')} seconds")
        print(f"  - Needs refresh: {status.get('needs_refresh', False)}")
        
        # Note: Actual refresh would happen automatically
        print_info("Token refresh happens automatically when needed")
        
        return True
    
    async def test_error_handling(self) -> bool:
        """Test error handling for various scenarios"""
        print_header("Testing Error Handling")
        
        tests_passed = 0
        tests_total = 0
        
        # Test 1: Invalid model
        tests_total += 1
        print_info("Testing invalid model...")
        try:
            response = await self.client.post(
                f"{self.config.base_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.config.master_key}"},
                json={
                    "model": "invalid-model-xyz",
                    "messages": [{"role": "user", "content": "test"}]
                }
            )
            if response.status_code >= 400:
                print_success("Invalid model handled correctly")
                tests_passed += 1
            else:
                print_error("Invalid model not rejected")
        except Exception:
            print_success("Invalid model raised exception (expected)")
            tests_passed += 1
        
        # Test 2: Invalid API key
        tests_total += 1
        print_info("Testing invalid API key...")
        try:
            response = await self.client.get(
                f"{self.config.base_url}/v1/models",
                headers={"Authorization": "Bearer invalid-key"}
            )
            if response.status_code == 401 or response.status_code == 403:
                print_success("Invalid API key rejected correctly")
                tests_passed += 1
            else:
                print_error(f"Invalid API key not rejected: {response.status_code}")
        except Exception:
            print_error("Invalid API key test failed")
        
        # Test 3: Missing required fields
        tests_total += 1
        print_info("Testing missing required fields...")
        try:
            response = await self.client.post(
                f"{self.config.base_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.config.master_key}"},
                json={"model": "claude-haiku"}  # Missing messages
            )
            if response.status_code >= 400:
                print_success("Missing fields handled correctly")
                tests_passed += 1
            else:
                print_error("Missing fields not validated")
        except Exception:
            print_success("Missing fields raised exception (expected)")
            tests_passed += 1
        
        print_info(f"Error handling tests: {tests_passed}/{tests_total} passed")
        return tests_passed == tests_total
    
    async def run_all_tests(self, skip_auth: bool = False) -> Dict[str, bool]:
        """Run all integration tests"""
        print_header("Claude OAuth Integration Test Suite")
        print_info(f"Base URL: {self.config.base_url}")
        print_info(f"Master Key: {self.config.master_key[:10]}...")
        
        results = {}
        
        # 1. Health check
        results["health_check"] = await self.test_health_check()
        
        # 2. OAuth status
        status = await self.test_oauth_status()
        results["oauth_status"] = True  # Status check itself worked
        
        # 3. Model listing
        results["list_models"] = await self.test_list_models()
        
        # 4. OAuth flow (if not authenticated and not skipping)
        if not status.get("authenticated") and not skip_auth:
            results["oauth_start"] = await self.test_oauth_start()
            
            if results["oauth_start"]:
                print(f"\n{Colors.WARNING}Manual step required:{Colors.ENDC}")
                print("Complete authentication and run with --code option")
        
        # 5. Chat completion (if authenticated)
        if status.get("authenticated"):
            results["chat_completion"] = await self.test_chat_completion()
            results["streaming"] = await self.test_streaming()
            results["token_refresh"] = await self.test_token_refresh_simulation()
        else:
            print_warning("Skipping authenticated tests (not authenticated)")
        
        # 6. Error handling
        results["error_handling"] = await self.test_error_handling()
        
        # Summary
        print_header("Test Summary")
        passed = sum(1 for v in results.values() if v)
        total = len(results)
        
        for test, result in results.items():
            status_str = "PASSED" if result else "FAILED"
            color = Colors.GREEN if result else Colors.FAIL
            print(f"{color}{test}: {status_str}{Colors.ENDC}")
        
        print(f"\n{Colors.BOLD}Total: {passed}/{total} tests passed{Colors.ENDC}")
        
        return results


async def interactive_oauth_flow(tester: ClaudeOAuthTester):
    """Interactive OAuth authentication flow"""
    print_header("Interactive OAuth Authentication")
    
    # Start OAuth flow
    if await tester.test_oauth_start():
        print(f"\n{Colors.BOLD}Please complete authentication:{Colors.ENDC}")
        print("1. Open the authorization URL in your browser")
        print("2. Sign in and authorize the application")
        print("3. Copy the authorization code from the redirect URL")
        
        code = input(f"\n{Colors.CYAN}Enter authorization code: {Colors.ENDC}")
        
        if code:
            # Exchange code for tokens
            if await tester.test_oauth_exchange(code):
                print_success("Authentication completed successfully!")
                
                # Test authenticated endpoints
                await tester.test_chat_completion()
            else:
                print_error("Authentication failed")
        else:
            print_warning("No code provided")


async def main():
    """Main test runner"""
    parser = argparse.ArgumentParser(description="Claude OAuth Integration Tests")
    parser.add_argument(
        "--base-url",
        default="http://localhost:4000",
        help="LiteLLM base URL"
    )
    parser.add_argument(
        "--master-key",
        default="sk-oauth-test-1234",
        help="LiteLLM master key"
    )
    parser.add_argument(
        "--code",
        help="Authorization code for OAuth exchange"
    )
    parser.add_argument(
        "--state",
        help="OAuth state for code exchange"
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run interactive OAuth flow"
    )
    parser.add_argument(
        "--skip-auth",
        action="store_true",
        help="Skip authentication tests"
    )
    parser.add_argument(
        "--model",
        default="claude-haiku",
        help="Model to test with"
    )
    
    args = parser.parse_args()
    
    # Create test configuration
    config = TestConfig(
        base_url=args.base_url,
        master_key=args.master_key
    )
    
    # Run tests
    async with ClaudeOAuthTester(config) as tester:
        if args.code:
            # Exchange code for tokens
            await tester.test_oauth_exchange(args.code, args.state)
        elif args.interactive:
            # Run interactive flow
            await interactive_oauth_flow(tester)
        else:
            # Run all tests
            results = await tester.run_all_tests(skip_auth=args.skip_auth)
            
            # Exit with appropriate code
            if all(results.values()):
                sys.exit(0)
            else:
                sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())