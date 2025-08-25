"use client"

import React, { useState, useEffect } from "react"
import { Badge, Callout } from "@tremor/react"
import { CheckCircleIcon, XCircleIcon } from "@heroicons/react/outline"
import { getClaudeOAuthStatus } from "./networking"

interface OAuthStatus {
  authenticated: boolean
  expires_in?: number
  needs_refresh?: boolean
}

interface ClaudeOAuthStatusBadgeProps {
  accessToken: string | null
}

export default function ClaudeOAuthStatusBadge({ accessToken }: ClaudeOAuthStatusBadgeProps) {
  const [oauthStatus, setOauthStatus] = useState<OAuthStatus | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    checkOAuthStatus()
    // Check status every minute
    const interval = setInterval(checkOAuthStatus, 60000)
    return () => clearInterval(interval)
  }, [accessToken])

  const checkOAuthStatus = async () => {
    if (!accessToken) {
      setOauthStatus({ authenticated: false })
      setLoading(false)
      return
    }
    try {
      const status = await getClaudeOAuthStatus(accessToken)
      setOauthStatus(status)
    } catch (error) {
      console.error("Failed to check OAuth status:", error)
      setOauthStatus({ authenticated: false })
    } finally {
      setLoading(false)
    }
  }

  if (loading || !oauthStatus) {
    return null
  }

  const getStatusColor = () => {
    if (oauthStatus.authenticated) {
      if (oauthStatus.needs_refresh) return "yellow"
      return "green"
    }
    return "gray"
  }

  const getStatusText = () => {
    if (oauthStatus.authenticated) {
      if (oauthStatus.needs_refresh) return "Claude OAuth: Token Expiring Soon"
      return "Claude OAuth: Connected"
    }
    return "Claude OAuth: Not Connected"
  }

  const getIcon = () => {
    if (oauthStatus.authenticated) {
      return CheckCircleIcon
    }
    return XCircleIcon
  }

  return (
    <div className="mb-4">
      <Callout
        title={getStatusText()}
        icon={getIcon()}
        color={getStatusColor()}
      >
        {oauthStatus.authenticated ? (
          <>
            Claude models are available with OAuth authentication.
            {oauthStatus.needs_refresh && " Token will expire soon - please refresh in Settings."}
          </>
        ) : (
          <>
            Connect your Claude account in Settings → Claude OAuth to use Claude models.
          </>
        )}
      </Callout>
    </div>
  )
}