import React from 'react'
import {
  Mic,
  Activity,
  Bell,
  MessageSquare,
  PhoneOff,
  ChevronRight,
} from 'lucide-react'

export default function ProtectionPipeline({
  transcriptsCount = 0,
  detectedCount = 0,
  riskTier = 'SAFE',
  riskScore = 0,
  caregiverRecord = null,
  userWarningRecord = null,
  interventionRecord = null,
}) {
  const isDetectionActive = transcriptsCount > 0 || detectedCount > 0
  const isRiskEvaluated = riskScore > 0 || riskTier !== 'SAFE'

  const steps = [
    {
      id: 'detection',
      label: 'Detection',
      shortLabel: 'DETECTION',
      icon: Mic,
      status: isDetectionActive ? 'ACTIVE' : 'IDLE',
      compactStatus: isDetectionActive ? 'ACTIVE' : 'IDLE',
      statusClass: isDetectionActive ? 'active' : 'idle',
      detail:
        detectedCount > 0
          ? `${detectedCount} Tactics Confirmed`
          : isDetectionActive
          ? 'Analyzing Audio'
          : 'Monitoring Stream',
    },
    {
      id: 'risk',
      label: 'Risk Assessed',
      shortLabel: 'RISK',
      icon: Activity,
      status: isRiskEvaluated ? riskTier : 'SAFE',
      compactStatus: isRiskEvaluated ? riskTier : 'SAFE',
      statusClass: isRiskEvaluated ? `tier-${riskTier.toLowerCase()}` : 'tier-safe',
      detail: `Score ${riskScore.toFixed(0)} / 100`,
    },
    {
      id: 'warning',
      label: 'Protected User',
      shortLabel: 'USER',
      icon: Bell,
      status: userWarningRecord?.status || 'NOT TRIGGERED',
      compactStatus: userWarningRecord?.status === 'DELIVERED' ? 'DELIVERED' : 'ARMED',
      statusClass: userWarningRecord?.status === 'DELIVERED' ? 'delivered' : 'not-triggered',
      detail: userWarningRecord?.message || 'Armed (In-call Voice Advisory)',
    },
    {
      id: 'caregiver',
      label: 'Caregiver Alert',
      shortLabel: 'CAREGIVER',
      icon: MessageSquare,
      status: caregiverRecord?.status || 'NOT TRIGGERED',
      compactStatus: caregiverRecord?.status === 'SENT' ? 'SENT' : 'ARMED',
      statusClass: caregiverRecord?.status === 'SENT' ? 'sent' : 'not-triggered',
      detail: caregiverRecord?.message || 'Armed (Emergency Mock SMS)',
    },
    {
      id: 'intervention',
      label: 'Intervention',
      shortLabel: 'INTERVENE',
      icon: PhoneOff,
      status: interventionRecord?.status || 'NOT TRIGGERED',
      compactStatus: interventionRecord?.status === 'EXECUTED' ? 'EXECUTED' : 'ARMED',
      statusClass: interventionRecord?.status === 'EXECUTED' ? 'executed' : 'not-triggered',
      detail: interventionRecord?.reason || 'Armed (Telephony Severance)',
    },
  ]

  return (
    <div className="protection-pipeline-card">
      <div className="pipeline-header">
        <span className="pipeline-title">Active Protection Pipeline</span>
        <span className="pipeline-indicator-live">
          <span className="pipeline-dot" />
          SESSION DEFENSE STATE
        </span>
      </div>

      <div className="pipeline-track">
        {steps.map((step, idx) => {
          const Icon = step.icon
          const isLast = idx === steps.length - 1

          return (
            <React.Fragment key={step.id}>
              <div
                className={`pipeline-step ${step.statusClass}`}
                title={`${step.label}: ${step.compactStatus} — ${step.detail}`}
              >
                <div className={`step-icon-box ${step.statusClass}`}>
                  <Icon size={11} />
                </div>
                <div className="step-content">
                  <span className="step-label font-mono">{step.shortLabel}</span>
                  <span className={`step-status-tag ${step.statusClass}`}>
                    {step.compactStatus}
                  </span>
                </div>
              </div>

              {!isLast && (
                <div
                  className={`pipeline-connector ${
                    steps[idx + 1].statusClass !== 'not-triggered' &&
                    steps[idx + 1].statusClass !== 'idle'
                      ? 'active'
                      : 'inactive'
                  }`}
                  aria-hidden="true"
                >
                  <ChevronRight size={12} className="connector-arrow" />
                </div>
              )}
            </React.Fragment>
          )
        })}
      </div>
    </div>
  )
}
