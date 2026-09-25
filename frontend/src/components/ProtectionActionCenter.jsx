import React from 'react'
import { ShieldCheck, ShieldAlert, AlertCircle } from 'lucide-react'
import ProtectionPipeline from './ProtectionPipeline'
import CaregiverCard from './CaregiverCard'
import UserWarningCard from './UserWarningCard'
import InterventionCard from './InterventionCard'

export default function ProtectionActionCenter({
  riskTier = 'SAFE',
  riskScore = 0,
  hasAlert = false,
  mode = 'STANDBY',
  transcriptsCount = 0,
  detectedCount = 0,
  explanation = '',
  caregiverRecord = null,
  userWarningRecord = null,
  interventionRecord = null,
  calleeName = 'Lakshmi R.',
  cooldownSuppressed = false,
}) {
  const isHighRisk = riskTier === 'HIGH' || riskTier === 'CRITICAL' || hasAlert

  return (
    <section className="glass-panel protection-action-center" aria-label="Protection Action Center">
      <div className="action-center-header">
        <div className="action-center-title-group">
          <ShieldCheck size={16} color="#38bdf8" />
          <h2 className="action-center-title">PROTECTION ACTIVE</h2>
        </div>

        <div className="action-center-status-badge">
          <span className={`defense-pulse-dot ${isHighRisk ? 'critical' : 'active'}`} />
          <span>{isHighRisk ? 'SAFEGUARDS TRIGGERED' : 'MONITORING'}</span>
        </div>
      </div>

      {/* 1. Visual Stage Progression Pipeline */}
      <ProtectionPipeline
        transcriptsCount={transcriptsCount}
        detectedCount={detectedCount}
        riskTier={riskTier}
        riskScore={riskScore}
        caregiverRecord={caregiverRecord}
        userWarningRecord={userWarningRecord}
        interventionRecord={interventionRecord}
      />

      {/* 2. Three Distinct Downstream Execution Cards */}
      <div className="action-cards-grid">
        <CaregiverCard caregiverRecord={caregiverRecord} cooldownSuppressed={cooldownSuppressed} />
        <UserWarningCard userWarningRecord={userWarningRecord} calleeName={calleeName} />
        <InterventionCard interventionRecord={interventionRecord} />
      </div>
    </section>
  )
}
