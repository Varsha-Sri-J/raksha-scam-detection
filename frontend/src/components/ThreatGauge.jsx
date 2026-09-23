import React from 'react'
import { ShieldAlert, AlertTriangle, CheckCircle2, TrendingUp, Info } from 'lucide-react'

export default function ThreatGauge({ riskAssessment, detectedCount = 0 }) {
  const score = Math.max(0, Math.min(100, riskAssessment?.overall_score || 0))
  const tier = (riskAssessment?.risk_tier || 'SAFE').toUpperCase()
  const tierClass = tier.toLowerCase()
  const explanation = riskAssessment?.explanation || 'Baseline safe state.'

  // SVG Gauge calculations
  const radius = 80
  const circumference = 2 * Math.PI * radius
  const strokeDashoffset = circumference - (score / 100) * circumference

  const getTierIcon = () => {
    switch (tier) {
      case 'CRITICAL':
      case 'HIGH':
        return <ShieldAlert size={16} />
      case 'MEDIUM':
        return <AlertTriangle size={16} />
      case 'LOW':
      case 'SAFE':
      default:
        return <CheckCircle2 size={16} />
    }
  }

  const getTierDescription = () => {
    switch (tier) {
      case 'CRITICAL':
        return 'Immediate danger of severe fraud or coercion.'
      case 'HIGH':
        return 'Multiple aggressive manipulation tactics identified.'
      case 'MEDIUM':
        return 'Suspicious urgency or authority claims observed.'
      case 'LOW':
        return 'Minor indicators detected; monitoring actively.'
      case 'SAFE':
      default:
        return 'No malicious manipulation patterns detected.'
    }
  }

  return (
    <section className="glass-panel threat-panel">
      <div className="threat-panel-header">
        <div className="panel-title-group">
          <TrendingUp size={16} color="var(--accent-cyan)" />
          <h2 className="panel-heading">Current Risk Score</h2>
        </div>
        <span className="tactics-counter-pill" title={`${detectedCount} manipulation patterns confirmed`}>
          {detectedCount} / 8 Tactics
        </span>
      </div>

      {/* Hero Circular SVG Gauge */}
      <div className="threat-gauge-wrapper">
        <svg className="gauge-svg" viewBox="0 0 200 200">
          <circle className="gauge-bg" cx="100" cy="100" r={radius} />
          <circle
            className={`gauge-progress ${tierClass}`}
            cx="100"
            cy="100"
            r={radius}
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
          />
        </svg>

        <div className="gauge-value-container">
          <span className={`gauge-number ${tierClass}`}>
            {score.toFixed(0)}
          </span>
          <span className="gauge-scale">/ 100</span>
          <span className="gauge-label">Threat Level</span>
        </div>
      </div>

      {/* Tier Pill Badge */}
      <div className={`threat-tier-pill ${tierClass}`}>
        {getTierIcon()}
        <span>{tier} RISK</span>
      </div>

      <div className="threat-tier-subtext">
        {getTierDescription()}
      </div>

      {/* Natural Language Explanation Box */}
      <div className="threat-explanation-card">
        <div className="explanation-header">
          <Info size={12} color="var(--accent-cyan)" />
          <span>Risk Assessment Analysis</span>
        </div>
        <p className="explanation-text">{explanation}</p>
      </div>
    </section>
  )
}
