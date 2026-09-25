import React from 'react'
import { Bell, Clock } from 'lucide-react'

export default function UserWarningCard({ userWarningRecord = null, calleeName = 'Lakshmi R.' }) {
  const getStatusBadge = () => {
    if (!userWarningRecord) {
      return {
        label: 'NOT TRIGGERED',
        className: 'action-tag not-triggered',
      }
    }

    const providerTag = (userWarningRecord.provider || 'mock').toUpperCase()
    const status = userWarningRecord.status || 'UNKNOWN'

    if (status === 'DELIVERED') {
      return {
        label: `${providerTag} WARNING — DELIVERED`,
        className: 'action-tag delivered',
      }
    } else if (status === 'FAILED') {
      return {
        label: `${providerTag} WARNING — FAILED`,
        className: 'action-tag failed',
      }
    } else if (status === 'SKIPPED') {
      return {
        label: `${providerTag} WARNING — SKIPPED`,
        className: 'action-tag skipped',
      }
    }

    return {
      label: `${providerTag} WARNING — ${status}`,
      className: 'action-tag neutral',
    }
  }

  const badge = getStatusBadge()

  const formattedTime = userWarningRecord?.timestamp
    ? new Date(
        typeof userWarningRecord.timestamp === 'number' && userWarningRecord.timestamp < 1e12
          ? userWarningRecord.timestamp * 1000
          : userWarningRecord.timestamp
      ).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : null

  const isDelivered = userWarningRecord?.status === 'DELIVERED'

  return (
    <div className={`action-module ${isDelivered ? 'module-active' : ''}`}>
      <div className="module-header">
        <div className="module-title-group">
          <Bell size={14} className="module-icon icon-warning" />
          <span className="module-title">Protected User</span>
        </div>
        <span className={badge.className}>{badge.label}</span>
      </div>

      <div className="module-meta">
        <span className="module-recipient font-mono">
          Target: {calleeName} · In-Call Audio Advisory
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
          {userWarningRecord?.message
            ? `"${userWarningRecord.message}"`
            : 'Standby — synthetic voice advisory injects directly into callee line if threat escalates to high/critical tier.'}
        </p>
      </div>
    </div>
  )
}
