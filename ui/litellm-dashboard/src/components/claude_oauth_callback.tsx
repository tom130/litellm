"use client"

import React, { useEffect, useState } from "react"
import { useSearchParams, useRouter } from "next/navigation"
import { Spin, message, Result } from "antd"
import { completeClaudeOAuth } from "./networking"

/**
 * OAuth Callback Handler Component
 * This component handles the OAuth callback from Claude
 */
export default function ClaudeOAuthCallback() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const [processing, setProcessing] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    handleCallback()
  }, [searchParams])

  const handleCallback = async () => {
    const code = searchParams.get("code")
    const state = searchParams.get("state")
    const error = searchParams.get("error")
    const errorDescription = searchParams.get("error_description")

    if (error) {
      setError(errorDescription || error)
      setProcessing(false)
      message.error(`OAuth error: ${errorDescription || error}`)
      
      // Close window if in popup
      if (window.opener) {
        setTimeout(() => {
          window.close()
        }, 3000)
      }
      return
    }

    if (!code || !state) {
      setError("Missing authorization code or state")
      setProcessing(false)
      return
    }

    // Verify state matches what we stored
    const storedState = sessionStorage.getItem("claude_oauth_state")
    if (storedState !== state) {
      setError("Invalid state parameter - possible CSRF attack")
      setProcessing(false)
      return
    }

    try {
      // Get access token from localStorage
      const accessToken = localStorage.getItem("accessToken")
      if (!accessToken) {
        setError("No access token found. Please log in.")
        setProcessing(false)
        return
      }
      
      // Complete OAuth flow
      const result = await completeClaudeOAuth(accessToken, code, state)
      
      if (result.success) {
        message.success("Claude OAuth connected successfully!")
        
        // Clear stored state
        sessionStorage.removeItem("claude_oauth_state")
        
        // If in popup, close it
        if (window.opener) {
          window.opener.postMessage({ type: "oauth-success" }, "*")
          window.close()
        } else {
          // If not in popup, redirect to settings
          router.push("/settings?tab=claude-oauth")
        }
      } else {
        throw new Error(result.message || "Failed to complete OAuth")
      }
    } catch (err: any) {
      setError(err.message || "Failed to complete OAuth flow")
      setProcessing(false)
      message.error("Failed to complete OAuth authentication")
      
      // Close popup after delay
      if (window.opener) {
        setTimeout(() => {
          window.close()
        }, 3000)
      }
    }
  }

  if (processing) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen">
        <Spin size="large" />
        <p className="mt-4 text-gray-600">Completing OAuth authentication...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Result
          status="error"
          title="OAuth Authentication Failed"
          subTitle={error}
          extra={
            window.opener ? (
              <p>This window will close automatically...</p>
            ) : (
              <button
                onClick={() => router.push("/settings")}
                className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
              >
                Back to Settings
              </button>
            )
          }
        />
      </div>
    )
  }

  return (
    <div className="flex items-center justify-center min-h-screen">
      <Result
        status="success"
        title="OAuth Authentication Successful"
        subTitle="You have successfully connected your Claude account."
        extra={
          window.opener ? (
            <p>This window will close automatically...</p>
          ) : (
            <button
              onClick={() => router.push("/settings")}
              className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
            >
              Go to Settings
            </button>
          )
        }
      />
    </div>
  )
}