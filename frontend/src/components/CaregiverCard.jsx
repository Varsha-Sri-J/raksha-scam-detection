import React from 'react'
import { MessageSquare, Clock } from 'lucide-react'

export default function CaregiverCard({
  caregiverRecord = null,
  defaultRecipient = '+91 91234 56789',
  cooldownSuppressed = false,
}) {
  // Format masked phone number (+91 91234 •••••)
  const formatMaskedPhone = (phone) => {
    if (!phone) return '+91 91234 •••••'
    const cleaned = String(phone).trim()
    if (cleaned.length >= 8) {
      return `${cleaned.slice(0, 8)} •••••`
    }
    return cleaned
  }

  const getStatusBadge = () => {
    if (!caregiverRecord) {
      if (cooldownSuppressed) {
        return {
          label: 'ALERT SUPPRESSED — COOLDOWN',
          className: 'action-tag skipped',
        }
      }
      return {
        label: 'NOT TRIGGERED',
        className: 'action-tag not-triggered',
      }
    }

    const providerTag = (caregiverRecord.provider || 'mock').toUpperCase()
    const status = caregiverRecord.status || 'UNKNOWN'

    if (status === 'SENT') {
      return {
        label: `${providerTag} SMS — SENT`,
        className: 'action-tag sent',
      }
    } else if (status === 'FAILED') {
      return {
        label: `${providerTag} SMS — FAILED`,
        className: 'action-tag failed',
      }
    } else if (status === 'SKIPPED') {
      return {
        label: `${providerTag} SMS — SKIPPED`,
        className: 'action-tag skipped',
      }
    }

    return {
      label: `${providerTag} SMS — ${status}`,
      className: 'action-tag neutral',
    }
  }

  const badge = getStatusBadge()
  const recipient = caregiverRecord?.recipient || defaultRecipient
  const maskedNumber = formatMaskedPhone(recipient)

  const formattedTime = caregiverRecord?.timestamp
    ? new Date(
        typeof caregiverRecord.timestamp === 'number' && caregiverRecord.timestamp < 1e12
          ? caregiverRecord.timestamp * 1000
          : caregiverRecord.timestamp
      ).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : null

  const isSent = caregiverRecord?.status === 'SENT'

  return (
    <div className={`action-module ${isSent ? 'module-active' : ''}`}>
      <div className="module-header">
        <div className="module-title-group">
          <MessageSquare size={14} className="module-icon icon-family" />
          <span className="module-title">CAREGIVER ALERT</span>
        </div>
        <span className={badge.className}>{badge.label}</span>
      </div>

      <div className="module-meta">
        <span className="module-recipient font-mono">
          Ananya R. · Daughter · {maskedNumber}
        </span>
        {formattedTime && (
          <span className="module-time font-mono">
            <Clock size={10} style={{ marginRight: 3, verticalAlign: 'middle' }} />
            {formattedTime}
          </span>
        )}
      </div>

      <div className="module-body">
        <p className="module-text">
          {caregiverRecord?.message
            ? `"${caregiverRecord.message}"`
            : 'Standby — automated mock SMS dispatches to emergency contact upon acute coercion or high-threat escalation.'}
        </p>
      </div>
    </div>
  )
}
