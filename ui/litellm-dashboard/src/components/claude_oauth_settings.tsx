"use client"

import React, { useState, useEffect } from "react"
import {
  Card,
  Title,
  Text,
  Button,
  Badge,
  Grid,
  Col,
  Callout,
  Subtitle,
  TextInput,
} from "@tremor/react"
import { Switch } from "antd"
import { 
  CheckCircleIcon, 
  XCircleIcon, 
  RefreshIcon,
  LinkIcon,
  ClockIcon,
  ExclamationIcon,
  ClipboardCopyIcon,
  KeyIcon,
} from "@heroicons/react/outline"
import { message, Spin, Modal, Input } from "antd"
import {
  getClaudeOAuthStatus,
  startClaudeOAuth,
  refreshClaudeToken,
  disconnectClaudeOAuth,
} from "./networking"

interface OAuthStatus {
  authenticated: boolean
  user_id?: string
  expires_in?: number
  needs_refresh?: boolean
  error?: string
}

interface ClaudeOAuthSettingsProps {
  accessToken: string | null
}

export default function ClaudeOAuthSettings({ accessToken }: ClaudeOAuthSettingsProps) {
  const [oauthStatus, setOauthStatus] = useState<OAuthStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [manualMode, setManualMode] = useState(false)
  const [manualCode, setManualCode] = useState("")
  const [submittingCode, setSubmittingCode] = useState(false)

  useEffect(() => {
    checkOAuthStatus()
    // Check status every 30 seconds
    const interval = setInterval(checkOAuthStatus, 30000)
    return () => clearInterval(interval)
  }, [accessToken])

  const checkOAuthStatus = async () => {
    if (!accessToken) return
    try {
      const status = await getClaudeOAuthStatus(accessToken)
      setOauthStatus(status)
    } catch (error) {
      console.error("Failed to check OAuth status:", error)
      setOauthStatus({ authenticated: false })
    }
  }

  const handleManualSubmit = async () => {
    if (!accessToken) {
      message.error("No access token available")
      return
    }
    
    if (!manualCode.trim()) {
      message.error("Please enter an authentication code")
      return
    }
    
    setSubmittingCode(true)
    try {
      // Submit the code directly to the callback endpoint
      const response = await fetch("/auth/claude/callback", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          code: manualCode.trim(),
          state: "manual_entry", // Special state for manual entry
        }),
      })
      
      let data
      try {
        data = await response.json()
      } catch (jsonError) {
        // If response is not JSON, use text
        const text = await response.text()
        data = { detail: text || "Invalid response from server" }
      }
      
      if (response.ok && data.success) {
        message.success("Authentication successful!")
        setManualCode("")
        setManualMode(false)
        await checkOAuthStatus()
      } else {
        // Better error handling
        const errorMessage = data.detail || data.message || data.error || "Failed to authenticate with the provided code"
        
        if (errorMessage.includes("Invalid") || errorMessage.includes("expired")) {
          message.error("Invalid or expired authentication code. Please get a new code from Claude.")
        } else if (errorMessage.includes("422")) {
          message.error("Invalid code format. Please copy the entire code from Claude.")
        } else {
          message.error(errorMessage)
        }
        
        console.error("OAuth error details:", data)
      }
    } catch (error) {
      console.error("Manual code submission error:", error)
      message.error("Network error: Failed to submit authentication code")
    } finally {
      setSubmittingCode(false)
    }
  }

  const handleConnect = async () => {
    if (!accessToken) {
      message.error("No access token available")
      return
    }
    
    if (manualMode) {
      // In manual mode, just show instructions
      message.info("Please copy the authentication code from Claude and paste it below")
      return
    }
    
    setConnecting(true)
    try {
      const response = await startClaudeOAuth(accessToken)
      
      if (response.authorization_url) {
        // Open OAuth flow in a popup window
        const width = 600
        const height = 700
        const left = window.screen.width / 2 - width / 2
        const top = window.screen.height / 2 - height / 2
        
        const popup = window.open(
          response.authorization_url,
          "claude-oauth",
          `width=${width},height=${height},left=${left},top=${top},toolbar=no,menubar=no`
        )
        
        // Check if popup was blocked
        if (!popup || popup.closed) {
          message.warning("Popup was blocked. Please use manual mode or allow popups for this site")
          setManualMode(true)
          setConnecting(false)
          return
        }
        
        // Poll for completion
        const pollTimer = setInterval(() => {
          try {
            if (popup.closed) {
              clearInterval(pollTimer)
              setConnecting(false)
              // Check status after popup closes
              setTimeout(checkOAuthStatus, 1000)
            }
          } catch (e) {
            clearInterval(pollTimer)
            setConnecting(false)
          }
        }, 1000)
        
        // Store state for callback handling
        if (response.state) {
          sessionStorage.setItem("claude_oauth_state", response.state)
        }
      }
    } catch (error) {
      message.error("Failed to start OAuth flow")
      console.error("OAuth error:", error)
    } finally {
      setConnecting(false)
    }
  }

  const handleRefresh = async () => {
    if (!accessToken) {
      message.error("No access token available")
      return
    }
    setRefreshing(true)
    try {
      const result = await refreshClaudeToken(accessToken)
      if (result.success) {
        message.success("Token refreshed successfully")
        await checkOAuthStatus()
      } else {
        message.error("Failed to refresh token")
      }
    } catch (error) {
      message.error("Failed to refresh token")
      console.error("Refresh error:", error)
    } finally {
      setRefreshing(false)
    }
  }

  const handleDisconnect = () => {
    if (!accessToken) {
      message.error("No access token available")
      return
    }
    Modal.confirm({
      title: "Disconnect Claude OAuth?",
      content: "This will remove your Claude authentication. You'll need to reconnect to use Claude models.",
      okText: "Disconnect",
      okType: "danger",
      onOk: async () => {
        setLoading(true)
        try {
          const result = await disconnectClaudeOAuth(accessToken)
          if (result.success) {
            message.success("Disconnected successfully")
            setOauthStatus({ authenticated: false })
          } else {
            message.error("Failed to disconnect")
          }
        } catch (error) {
          message.error("Failed to disconnect")
          console.error("Disconnect error:", error)
        } finally {
          setLoading(false)
        }
      },
    })
  }

  const formatExpiryTime = (seconds?: number) => {
    if (!seconds) return "Unknown"
    
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    
    if (hours > 24) {
      const days = Math.floor(hours / 24)
      return `${days} day${days > 1 ? 's' : ''}`
    } else if (hours > 0) {
      return `${hours} hour${hours > 1 ? 's' : ''} ${minutes} min`
    } else if (minutes > 0) {
      return `${minutes} minute${minutes > 1 ? 's' : ''}`
    } else {
      return "Less than a minute"
    }
  }

  const getStatusColor = () => {
    if (!oauthStatus) return "gray"
    if (oauthStatus.authenticated) {
      if (oauthStatus.needs_refresh) return "yellow"
      return "green"
    }
    return "red"
  }

  const getStatusText = () => {
    if (!oauthStatus) return "Checking..."
    if (oauthStatus.authenticated) {
      if (oauthStatus.needs_refresh) return "Needs Refresh"
      return "Connected"
    }
    return "Not Connected"
  }

  return (
    <Card className="mt-4">
      <div className="flex items-center justify-between mb-4">
        <div>
          <Title>Claude OAuth Authentication</Title>
          <Text className="mt-1">
            Connect your Claude account to use Claude models through OAuth
          </Text>
        </div>
        <Badge color={getStatusColor()} size="lg">
          {getStatusText()}
        </Badge>
      </div>

      {oauthStatus?.authenticated ? (
        <>
          <Callout
            title="OAuth Connected"
            icon={CheckCircleIcon}
            color="green"
            className="mb-4"
          >
            Your Claude account is connected and authenticated.
          </Callout>

          <Grid numItems={1} numItemsSm={2} className="gap-4 mb-4">
            <Col>
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Text className="font-semibold">User ID:</Text>
                  <Text>{oauthStatus.user_id || "Unknown"}</Text>
                </div>
                <div className="flex items-center gap-2">
                  <ClockIcon className="h-4 w-4 text-gray-500" />
                  <Text className="font-semibold">Token expires in:</Text>
                  <Text className={oauthStatus.needs_refresh ? "text-yellow-600" : ""}>
                    {formatExpiryTime(oauthStatus.expires_in)}
                  </Text>
                </div>
              </div>
            </Col>
            <Col>
              <div className="flex gap-2 justify-end">
                <Button
                  size="sm"
                  variant="secondary"
                  icon={RefreshIcon}
                  onClick={handleRefresh}
                  loading={refreshing}
                  disabled={refreshing}
                >
                  Refresh Token
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  color="red"
                  onClick={handleDisconnect}
                  loading={loading}
                  disabled={loading}
                >
                  Disconnect
                </Button>
              </div>
            </Col>
          </Grid>

          {oauthStatus.needs_refresh && (
            <Callout
              title="Token Expiring Soon"
              icon={ExclamationIcon}
              color="yellow"
            >
              Your token will expire soon. Click &quot;Refresh Token&quot; to extend your session.
            </Callout>
          )}
        </>
      ) : (
        <>
          <Callout
            title="Not Connected"
            icon={XCircleIcon}
            color="red"
            className="mb-4"
          >
            Connect your Claude account to enable OAuth authentication for Claude models.
          </Callout>

          <div className="space-y-4">
            {/* Mode Toggle */}
            <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
              <div className="flex items-center gap-2">
                <Text className="font-medium">Authentication Mode:</Text>
                <Badge color={manualMode ? "yellow" : "blue"}>
                  {manualMode ? "Manual" : "Automatic"}
                </Badge>
              </div>
              <Switch
                checked={manualMode}
                onChange={(checked) => setManualMode(checked)}
              />
            </div>

            {manualMode ? (
              <>
                <div className="bg-yellow-50 dark:bg-yellow-900/20 rounded-lg p-4">
                  <Subtitle className="mb-2 flex items-center gap-2">
                    <KeyIcon className="h-5 w-5" />
                    Manual Authentication
                  </Subtitle>
                  <ol className="list-decimal list-inside space-y-1 text-sm text-gray-600 dark:text-gray-400">
                    <li>Go to Claude and get your authentication code</li>
                    <li>Copy the entire code</li>
                    <li>Paste it in the field below</li>
                    <li>Click &quot;Submit Code&quot; to authenticate</li>
                  </ol>
                </div>

                <div className="space-y-3">
                  <Text className="text-sm font-medium">Authentication Code:</Text>
                  <Input.TextArea
                    placeholder="Paste your Claude authentication code here..."
                    value={manualCode}
                    onChange={(e) => setManualCode(e.target.value)}
                    rows={3}
                    className="font-mono text-sm"
                  />
                  <div className="flex justify-center">
                    <Button
                      size="lg"
                      icon={CheckCircleIcon}
                      onClick={handleManualSubmit}
                      loading={submittingCode}
                      disabled={submittingCode || !manualCode.trim()}
                      color="green"
                      className="px-8"
                    >
                      {submittingCode ? "Submitting..." : "Submit Code"}
                    </Button>
                  </div>
                </div>
              </>
            ) : (
              <>
                <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
                  <Subtitle className="mb-2">Automatic Authentication:</Subtitle>
                  <ol className="list-decimal list-inside space-y-1 text-sm text-gray-600 dark:text-gray-400">
                    <li>Click &quot;Connect Claude Account&quot; below</li>
                    <li>Authorize LiteLLM in the popup window</li>
                    <li>Your tokens will be securely stored</li>
                    <li>Use Claude models with api_key=&quot;oauth&quot;</li>
                  </ol>
                </div>

                <div className="flex justify-center">
                  <Button
                    size="lg"
                    icon={LinkIcon}
                    onClick={handleConnect}
                    loading={connecting}
                    disabled={connecting}
                    className="px-8"
                  >
                    {connecting ? "Connecting..." : "Connect Claude Account"}
                  </Button>
                </div>
              </>
            )}

            {/* Help text */}
            <Callout
              title="Having trouble?"
              icon={ExclamationIcon}
              color="blue"
            >
              If the automatic method doesn&apos;t work (popup blocked or redirect issues), 
              switch to Manual mode and enter your authentication code directly.
            </Callout>
          </div>
        </>
      )}

      {loading && !refreshing && !connecting && (
        <div className="flex justify-center mt-4">
          <Spin />
        </div>
      )}
    </Card>
  )
}