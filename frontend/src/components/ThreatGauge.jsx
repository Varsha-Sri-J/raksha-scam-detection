import React from 'react'
import { ShieldAlert, AlertTriangle, CheckCircle2, TrendingUp, Shield } from 'lucide-react'

export default function ThreatGauge({
  riskAssessment,
  detectedCount = 0,
  peakScore = null,
}) {
  const score = Math.max(0, Math.min(100, riskAssessment?.overall_score || 0))
  const tier = (riskAssessment?.risk_tier || 'SAFE').toUpperCase()
  const tierClass = tier.toLowerCase()
  const explanation =
    riskAssessment?.explanation ||
    'Baseline safe state. Monitoring call audio stream for manipulation tactics.'

  // SVG Gauge calculations (compact 130x130)
  const radius = 52
  const circumference = 2 * Math.PI * radius
  const strokeDashoffset = circumference - (score / 100) * circumference

  const getTierIcon = () => {
    switch (tier) {
      case 'CRITICAL':
      case 'HIGH':
        return <ShieldAlert size={13} />
      case 'MEDIUM':
        return <AlertTriangle size={13} />
      case 'LOW':
      case 'SAFE':
      default:
        return <CheckCircle2 size={13} />
    }
  }

  return (
    <section className="glass-panel threat-panel" aria-label="Current Threat Assessment">
      {/* Header */}
      <div className="threat-panel-header">
        <div className="panel-title-group">
          <TrendingUp size={13} color="#38bdf8" />
          <h2 className="panel-heading">CURRENT RISK</h2>
        </div>
        {peakScore !== null && peakScore > score && (
          <span className="peak-score-pill font-mono" title="Highest threat score reached in session">
            Peak: {Math.round(peakScore)}
          </span>
        )}
      </div>

      {/* Compact Circular SVG Gauge (approx 150-170px) */}
      <div className="threat-gauge-wrapper">
        <svg className="gauge-svg" viewBox="0 0 130 130" aria-hidden="true">
          <circle className="gauge-bg" cx="65" cy="65" r={radius} />
          <circle
            className={`gauge-progress ${tierClass}`}
            cx="65"
            cy="65"
            r={radius}
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
          />
        </svg>

        <div className="gauge-value-container">
          <span className={`gauge-number ${tierClass} font-mono`}>
            {score.toFixed(0)}
          </span>
          <span className="gauge-scale font-mono">/ 100</span>
        </div>
      </div>

      {/* Risk Tier & Tactics Indicators */}
      <div className="threat-badges-row">
        <div className={`threat-tier-pill ${tierClass}`}>
          {getTierIcon()}
          <span>{tier} RISK</span>
        </div>
        <div className="tactics-counter-pill font-mono" title={`${detectedCount} manipulation patterns confirmed`}>
          {detectedCount} / 8 TACTICS
        </div>
      </div>

      {/* Why RAKSHA Acted - Compact Prominent Rationale Card */}
      <div className="threat-explanation-card">
        <div className="explanation-header">
          <Shield size={11} color="#38bdf8" />
          <span className="explanation-title">WHY RAKSHA ACTED</span>
        </div>
        <p className="explanation-text">
          {explanation}
        </p>
      </div>
    </section>
  )
}
