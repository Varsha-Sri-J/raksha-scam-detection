import React from 'react'
import { PhoneOff, Clock } from 'lucide-react'

export default function InterventionCard({ interventionRecord = null }) {
  const getStatusBadge = () => {
    if (!interventionRecord) {
      return {
        label: 'NOT TRIGGERED',
        className: 'action-tag not-triggered',
      }
    }

    const providerTag = (interventionRecord.provider || 'mock').toUpperCase()
    const status = interventionRecord.status || 'UNKNOWN'

    if (status === 'EXECUTED') {
      return {
        label: `${providerTag} — EXECUTED`,
        className: 'action-tag executed',
      }
    } else if (status === 'FAILED') {
      return {
        label: `${providerTag} — FAILED`,
        className: 'action-tag failed',
      }
    } else if (status === 'SUPPRESSED') {
      return {
        label: `${providerTag} — SUPPRESSED`,
        className: 'action-tag skipped',
      }
    }

    return {
      label: `${providerTag} — ${status}`,
      className: 'action-tag neutral',
    }
  }

  const badge = getStatusBadge()

  const formattedTime = interventionRecord?.timestamp
    ? new Date(
        typeof interventionRecord.timestamp === 'number' && interventionRecord.timestamp < 1e12
          ? interventionRecord.timestamp * 1000
          : interventionRecord.timestamp
      ).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : null

  const isExecuted = interventionRecord?.status === 'EXECUTED'

  return (
    <div className={`action-module ${isExecuted ? 'module-critical-active' : ''}`}>
      <div className="module-header">
        <div className="module-title-group">
          <PhoneOff size={14} className="module-icon icon-intervention" />
          <span className="module-title">Intervention</span>
        </div>
        <span className={badge.className}>{badge.label}</span>
      </div>

      <div className="module-meta">
        <span className="module-recipient font-mono">
          Telephony Severance · Inbound Call Leg
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
          {interventionRecord?.reason
            ? interventionRecord.reason
            : 'Standby — automated call severance executes if acute credential/financial extraction is verified under critical danger.'}
        </p>
      </div>
    </div>
  )
}
