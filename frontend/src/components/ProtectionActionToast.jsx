import React, { useState, useEffect, useRef } from 'react'
import { ShieldCheck, Bell, PhoneOff, X } from 'lucide-react'

export default function ProtectionActionToast({
  latestCaregiver = null,
  latestUserWarning = null,
  latestIntervention = null,
}) {
  const [toasts, setToasts] = useState([])
  const lastCaregiverIdRef = useRef(null)
  const lastWarningIdRef = useRef(null)
  const lastInterventionIdRef = useRef(null)

  // Helper to add toast and auto-dismiss after 3.5s
  const addToast = (toast) => {
    setToasts((prev) => {
      if (prev.some((t) => t.id === toast.id)) return prev
      return [...prev, toast]
    })

    setTimeout(() => {
      dismissToast(toast.id)
    }, 3500)
  }

  const dismissToast = (id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }

  // Handle Caregiver notification trigger
  useEffect(() => {
    if (!latestCaregiver) {
      lastCaregiverIdRef.current = null
      return
    }

    const notifId = latestCaregiver.notification_id || `${latestCaregiver.timestamp}-${latestCaregiver.status}`
    if (latestCaregiver.status === 'SENT' && lastCaregiverIdRef.current !== notifId) {
      lastCaregiverIdRef.current = notifId
      const recipient = latestCaregiver.caregiver_name || latestCaregiver.recipient_name || 'Ananya R.'

      addToast({
        id: `toast-cg-${notifId}`,
        type: 'caregiver',
        icon: ShieldCheck,
        iconColor: '#10b981',
        title: '🛡 RAKSHA PROTECTION ACTION',
        subtitle: 'High-risk scam detected',
        description: 'Caregiver alert sent',
        badge: `${recipient} • MOCK SMS — SENT`,
        accentClass: 'toast-accent-emerald',
      })
    }
  }, [latestCaregiver])

  // Handle Protected User warning trigger
  useEffect(() => {
    if (!latestUserWarning) {
      lastWarningIdRef.current = null
      return
    }

    const warnId = latestUserWarning.warning_id || `${latestUserWarning.timestamp}-${latestUserWarning.status}`
    if (latestUserWarning.status === 'DELIVERED' && lastWarningIdRef.current !== warnId) {
      lastWarningIdRef.current = warnId

      addToast({
        id: `toast-warn-${warnId}`,
        type: 'user_warning',
        icon: Bell,
        iconColor: '#38bdf8',
        title: '🔔 PROTECTED USER WARNING',
        subtitle: 'In-call safety advisory delivered',
        description: '',
        badge: 'MOCK WARNING — DELIVERED',
        accentClass: 'toast-accent-cyan',
      })
    }
  }, [latestUserWarning])

  // Handle Intervention trigger
  useEffect(() => {
    if (!latestIntervention) {
      lastInterventionIdRef.current = null
      return
    }

    const intervId = latestIntervention.intervention_id || `${latestIntervention.timestamp}-${latestIntervention.status}`
    if (latestIntervention.status === 'EXECUTED' && lastInterventionIdRef.current !== intervId) {
      lastInterventionIdRef.current = intervId

      addToast({
        id: `toast-interv-${intervId}`,
        type: 'intervention',
        icon: PhoneOff,
        iconColor: '#f43f5e',
        title: '🛑 CALL INTERVENTION EXECUTED',
        subtitle: 'High-risk credential/financial extraction detected',
        description: '',
        badge: 'MOCK DISCONNECT — EXECUTED',
        accentClass: 'toast-accent-rose',
      })
    }
  }, [latestIntervention])

  // If all 3 are null (e.g. session reset), clear all active toasts
  useEffect(() => {
    if (!latestCaregiver && !latestUserWarning && !latestIntervention) {
      setToasts([])
      lastCaregiverIdRef.current = null
      lastWarningIdRef.current = null
      lastInterventionIdRef.current = null
    }
  }, [latestCaregiver, latestUserWarning, latestIntervention])

  if (toasts.length === 0) return null

  return (
    <div className="protection-toasts-container" role="region" aria-label="Protection Action Notifications">
      {toasts.map((toast) => {
        const IconComponent = toast.icon
        return (
          <div
            key={toast.id}
            className={`protection-toast-item ${toast.accentClass}`}
            role="status"
            aria-live="polite"
          >
            <div className="toast-icon-box">
              <IconComponent size={20} color={toast.iconColor} />
            </div>

            <div className="toast-body">
              <div className="toast-title-row">
                <span className="toast-title font-mono">{toast.title}</span>
              </div>
              <span className="toast-subtitle">{toast.subtitle}</span>
              {toast.description && (
                <span className="toast-desc">{toast.description}</span>
              )}
              <div className="toast-badge-box">
                <span className="toast-badge font-mono">{toast.badge}</span>
              </div>
            </div>

            <button
              type="button"
              className="toast-close-btn"
              onClick={() => dismissToast(toast.id)}
              aria-label="Dismiss notification"
            >
              <X size={14} />
            </button>
          </div>
        )
      })}
    </div>
  )
}
