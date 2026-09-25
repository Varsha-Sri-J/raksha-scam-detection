import React, { useState, useEffect } from 'react'
import {
  ShieldAlert,
  FileText,
  CheckCircle2,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  X,
  ExternalLink,
  Lock,
  Activity,
  Flame,
  PhoneCall,
  ArrowRight,
  Eye,
} from 'lucide-react'

export default function CampaignIntelligence({
  campaign: propCampaign = null,
  caregiverStatus = null,
  onCampaignUpdate = null,
}) {
  const [activeCampaign, setActiveCampaign] = useState(propCampaign)
  const [report, setReport] = useState(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [isExpanded, setIsExpanded] = useState(true)
  const [isReportModalOpen, setIsReportModalOpen] = useState(false)
  const [errorMsg, setErrorMsg] = useState(null)

  // Sync with prop when parent passes campaign updates (e.g. via WebSocket)
  useEffect(() => {
    if (propCampaign) {
      setActiveCampaign(propCampaign)
    }
  }, [propCampaign])

  // Initial fetch: check if any campaign exists on backend
  useEffect(() => {
    let isMounted = true
    const fetchCampaigns = async () => {
      try {
        const res = await fetch('/api/campaigns')
        if (res.ok) {
          const campaigns = await res.json()
          if (isMounted && campaigns && campaigns.length > 0) {
            // Pick most recent active campaign
            setActiveCampaign(campaigns[0])
          }
        }
      } catch (err) {
        // Silent fail for standby
      }
    }

    if (!propCampaign) {
      fetchCampaigns()
    }
    return () => {
      isMounted = false
    }
  }, [propCampaign])

  // Check if report already exists for this campaign
  useEffect(() => {
    let isMounted = true
    const checkReport = async () => {
      if (!activeCampaign?.campaign_id) return
      try {
        const res = await fetch(`/api/campaigns/${activeCampaign.campaign_id}/report`)
        if (res.ok) {
          const data = await res.json()
          if (isMounted) {
            setReport(data)
          }
        }
      } catch (e) {
        // No report yet
      }
    }
    checkReport()
    return () => {
      isMounted = false
    }
  }, [activeCampaign?.campaign_id])

  // Handle report generation with subtle SOC transition animation
  const handleGenerateReport = async () => {
    if (!activeCampaign?.campaign_id) return
    setIsGenerating(true)
    setErrorMsg(null)

    try {
      const res = await fetch(`/api/campaigns/${activeCampaign.campaign_id}/report`, {
        method: 'POST',
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || `Failed to generate report (${res.status})`)
      }

      const generatedReport = await res.json()
      // Professional transition delay
      setTimeout(() => {
        setReport(generatedReport)
        setIsGenerating(false)
        setActiveCampaign((prev) =>
          prev ? { ...prev, status: 'REPORT_GENERATED' } : prev
        )
        if (onCampaignUpdate) {
          onCampaignUpdate({ ...activeCampaign, status: 'REPORT_GENERATED' })
        }
      }, 700)
    } catch (err) {
      setIsGenerating(false)
      setErrorMsg(err.message || 'Error generating report')
    }
  }

  // Format date helper
  const formatDate = (ts) => {
    if (!ts) return 'N/A'
    const ms = ts < 1e12 ? ts * 1000 : ts
    return new Date(ms).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }

  // Determine status display
  const getStatusBadge = () => {
    if (!activeCampaign) return null

    if (isGenerating) {
      return (
        <span className="campaign-status-pill status-generating font-mono">
          <Activity size={12} className="spin-icon" /> REPORT GENERATING...
        </span>
      )
    }

    switch (activeCampaign.status) {
      case 'REPORT_GENERATED':
        return (
          <span className="campaign-status-pill status-reported font-mono">
            <CheckCircle2 size={12} /> REPORT GENERATED
          </span>
        )
      case 'ESCALATION_ELIGIBLE':
        return (
          <span className="campaign-status-pill status-eligible font-mono">
            <AlertTriangle size={12} /> 🚨 ESCALATION ELIGIBLE
          </span>
        )
      case 'ACTIVE_MONITORING':
        return (
          <span className="campaign-status-pill status-monitoring font-mono">
            <span className="pulse-dot-amber" /> ACTIVE MONITORING
          </span>
        )
      case 'DETECTED':
      default:
        return (
          <span className="campaign-status-pill status-detected font-mono">
            <span className="pulse-dot-blue" /> CAMPAIGN DETECTED
          </span>
        )
    }
  }

  return (
    <section className="campaign-intelligence-section" aria-label="Campaign Link Intelligence">
      <div className="glass-panel campaign-panel">
        {/* Panel Header */}
        <div
          className="campaign-header"
          onClick={() => setIsExpanded(!isExpanded)}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => e.key === 'Enter' && setIsExpanded(!isExpanded)}
        >
          <div className="campaign-header-left">
            <ShieldAlert size={16} className="campaign-shield-icon" />
            <span className="campaign-title font-mono">CAMPAIGN INTELLIGENCE</span>
            {activeCampaign && (
              <span className="campaign-id-badge font-mono">
                {activeCampaign.campaign_id}
              </span>
            )}
            {getStatusBadge()}
          </div>

          <div className="campaign-header-right">
            {activeCampaign && (
              <span className="campaign-incident-count font-mono">
                Linked Incidents: {activeCampaign.incident_count}
              </span>
            )}
            <button
              type="button"
              className="campaign-toggle-btn"
              aria-label={isExpanded ? 'Collapse campaign intelligence' : 'Expand campaign intelligence'}
            >
              {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </button>
          </div>
        </div>

        {/* Panel Content */}
        {isExpanded && (
          <div className="campaign-content">
            {!activeCampaign ? (
              <div className="campaign-empty-state">
                <p className="campaign-empty-text">No linked campaign detected.</p>
                <span className="campaign-empty-hint">
                  Repeated high or critical scam incidents with matching signatures will automatically link here.
                </span>
              </div>
            ) : (
              <div className="campaign-body">
                {/* Informational Caregiver Delivery Notice (Requirement 15) */}
                {caregiverStatus === 'FAILED' && (
                  <div className="caregiver-fallback-alert font-mono">
                    <AlertTriangle size={13} color="var(--color-medium)" />
                    <span>CAREGIVER ALERT: FAILED • DASHBOARD ESCALATION ACTIVE</span>
                  </div>
                )}

                {/* Metrics Grid */}
                <div className="campaign-grid">
                  <div className="campaign-metric-card">
                    <span className="metric-label font-mono">LINKED INCIDENTS</span>
                    <span className="metric-value font-mono highlight-number">
                      {activeCampaign.incident_count}
                    </span>
                    <span className="metric-sub font-mono">
                      Threshold: 3 for escalation
                    </span>
                  </div>

                  <div className="campaign-metric-card">
                    <span className="metric-label font-mono">CALLER IDENTIFIERS</span>
                    <div className="masked-callers-list font-mono">
                      {activeCampaign.observed_caller_identifiers &&
                      activeCampaign.observed_caller_identifiers.length > 0 ? (
                        activeCampaign.observed_caller_identifiers.map((cid, i) => (
                          <span key={i} className="masked-caller-pill">
                            <PhoneCall size={10} /> {cid}
                          </span>
                        ))
                      ) : (
                        <span className="masked-caller-pill muted">Unknown Caller</span>
                      )}
                    </div>
                    <span className="metric-sub font-mono">Masked for privacy</span>
                  </div>

                  <div className="campaign-metric-card">
                    <span className="metric-label font-mono">DOMINANT TACTICS</span>
                    <div className="campaign-tactics-list font-mono">
                      {activeCampaign.dominant_tactics && activeCampaign.dominant_tactics.length > 0 ? (
                        activeCampaign.dominant_tactics.slice(0, 3).map((t, i) => (
                          <span key={i} className="campaign-tactic-pill">
                            {typeof t === 'string' ? t.replace(/_/g, ' ') : t}
                          </span>
                        ))
                      ) : (
                        <span className="campaign-tactic-pill muted">Analyzing...</span>
                      )}
                    </div>
                    <span className="metric-sub font-mono">
                      Target: {activeCampaign.target_categories?.join(', ') || 'General'}
                    </span>
                  </div>

                  <div className="campaign-metric-card">
                    <span className="metric-label font-mono">HIGHEST / AVG RISK</span>
                    <div className="risk-comparison-row font-mono">
                      <span className="peak-risk-val">
                        {activeCampaign.highest_risk_score?.toFixed(0) || 0}
                      </span>
                      <span className="risk-divider">/</span>
                      <span className="avg-risk-val">
                        avg {activeCampaign.average_risk_score?.toFixed(0) || 0}
                      </span>
                    </div>
                    <span className="metric-sub font-mono">
                      Last Seen: {formatDate(activeCampaign.last_seen)}
                    </span>
                  </div>
                </div>

                {/* Escalation Action Bar */}
                <div className="campaign-actions-row">
                  {activeCampaign.status === 'ESCALATION_ELIGIBLE' && !report && (
                    <div className="escalation-prompt-box">
                      <div className="escalation-prompt-text font-mono">
                        <AlertTriangle size={15} color="var(--color-critical)" />
                        <span>
                          🚨 <strong>LAW-ENFORCEMENT ESCALATION ELIGIBLE:</strong> Campaign reached {activeCampaign.incident_count} linked incidents.
                        </span>
                      </div>
                      <button
                        type="button"
                        className="btn-campaign-escalate"
                        onClick={handleGenerateReport}
                        disabled={isGenerating}
                      >
                        {isGenerating ? (
                          <>
                            <Activity size={14} className="spin-icon" /> GENERATING...
                          </>
                        ) : (
                          <>
                            <FileText size={14} /> GENERATE REPORT
                          </>
                        )}
                      </button>
                    </div>
                  )}

                  {(report || activeCampaign.status === 'REPORT_GENERATED') && (
                    <div className="escalation-completed-box">
                      <div className="escalation-completed-text font-mono">
                        <CheckCircle2 size={15} color="var(--color-safe)" />
                        <div>
                          <span className="report-badge-title">
                            LAW-ENFORCEMENT REPORT: <strong>✓ MOCK REPORT GENERATED</strong>
                          </span>
                          <span className="report-id-text">
                            Report ID: {report?.report_id || 'RAKSHA-NCRP-ACTIVE'} • DEMO ONLY — NO ACTUAL TRANSMISSION
                          </span>
                        </div>
                      </div>
                      <button
                        type="button"
                        className="btn-campaign-view-report"
                        onClick={() => setIsReportModalOpen(true)}
                      >
                        <Eye size={14} /> VIEW REPORT
                      </button>
                    </div>
                  )}

                  {errorMsg && (
                    <div className="campaign-error-banner font-mono">
                      <AlertTriangle size={13} /> {errorMsg}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Mock Law Enforcement Dossier View Modal */}
      {isReportModalOpen && (
        <div className="inspector-overlay" onClick={() => setIsReportModalOpen(false)}>
          <div
            className="glass-panel report-modal"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="report-modal-title"
          >
            {/* Modal Header */}
            <div className="report-modal-header">
              <div className="report-title-group">
                <FileText size={20} color="var(--color-safe)" />
                <div>
                  <h3 id="report-modal-title" className="report-modal-title font-mono">
                    RAKSHA — CAMPAIGN INTELLIGENCE REPORT
                  </h3>
                  <span className="report-subtitle font-mono">
                    SYNTHETIC LAW-ENFORCEMENT INCIDENT DOSSIER
                  </span>
                </div>
              </div>
              <button
                type="button"
                className="inspector-close-btn"
                onClick={() => setIsReportModalOpen(false)}
                aria-label="Close report"
              >
                <X size={18} />
              </button>
            </div>

            {/* Modal Body */}
            <div className="report-modal-body">
              {/* Mandatory Prominent Disclaimer */}
              <div className="report-disclaimer-box font-mono">
                <Lock size={15} color="var(--color-medium)" />
                <div>
                  <strong>DEMO ONLY — NO ACTUAL TRANSMISSION TO LAW ENFORCEMENT</strong>
                  <p>
                    This is an in-memory intelligence dossier generated for demonstration purposes.
                    No communication has been sent to NCRP, I4C, police, or external authorities.
                  </p>
                </div>
              </div>

              {/* Dossier Meta Table */}
              <div className="report-meta-grid font-mono">
                <div className="report-meta-item">
                  <span className="meta-label">CAMPAIGN ID</span>
                  <span className="meta-val">{activeCampaign?.campaign_id}</span>
                </div>
                <div className="report-meta-item">
                  <span className="meta-label">REPORT ID</span>
                  <span className="meta-val text-cyan">{report?.report_id || 'RAKSHA-NCRP-PENDING'}</span>
                </div>
                <div className="report-meta-item">
                  <span className="meta-label">STATUS</span>
                  <span className="meta-val text-safe">{report?.status || 'MOCK_REPORT_GENERATED'}</span>
                </div>
                <div className="report-meta-item">
                  <span className="meta-label">TIMELINE</span>
                  <span className="meta-val">
                    {formatDate(report?.first_seen || activeCampaign?.first_seen)} →{' '}
                    {formatDate(report?.last_seen || activeCampaign?.last_seen)}
                  </span>
                </div>
              </div>

              {/* Linked Incidents & Caller Intelligence */}
              <div className="report-section">
                <h4 className="report-section-heading font-mono">LINKED INCIDENTS & CALLERS</h4>
                <div className="report-two-col font-mono">
                  <div className="report-subcard">
                    <span className="subcard-title">
                      LINKED INCIDENTS ({report?.incident_count || activeCampaign?.incident_count || 0})
                    </span>
                    <div className="incident-id-tags">
                      {(report?.linked_incident_ids || activeCampaign?.linked_incidents?.map((i) => i.incident_id) || []).map(
                        (id, idx) => (
                          <span key={idx} className="incident-id-tag">
                            #{id}
                          </span>
                        )
                      )}
                    </div>
                  </div>

                  <div className="report-subcard">
                    <span className="subcard-title">
                      CALLER IDENTIFIERS (
                      {(report?.observed_caller_identifiers || activeCampaign?.observed_caller_identifiers || []).length} masked)
                    </span>
                    <div className="masked-callers-dossier">
                      {(report?.observed_caller_identifiers || activeCampaign?.observed_caller_identifiers || []).map(
                        (cid, idx) => (
                          <span key={idx} className="masked-caller-pill">
                            <PhoneCall size={11} /> {cid}
                          </span>
                        )
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Common Attack Pattern & Progression */}
              <div className="report-section">
                <h4 className="report-section-heading font-mono">COMMON ATTACK PROGRESSION</h4>
                <div className="progression-flowchart font-mono">
                  {(report?.attack_progression_summary && report.attack_progression_summary.length > 0
                    ? report.attack_progression_summary
                    : ['AUTHORITY_IMPERSONATION', 'FEAR_INTIMIDATION', 'ISOLATION_SECRECY', 'FINANCIAL_REDIRECTION']
                  ).map((tactic, idx, arr) => (
                    <React.Fragment key={idx}>
                      <div className="progression-node">
                        <span className="node-num">0{idx + 1}</span>
                        <span className="node-text">{tactic.replace(/_/g, ' ')}</span>
                      </div>
                      {idx < arr.length - 1 && (
                        <div className="progression-arrow">
                          <ArrowRight size={14} />
                        </div>
                      )}
                    </React.Fragment>
                  ))}
                </div>
              </div>

              {/* Risk Profile & Escalation Reason */}
              <div className="report-section">
                <h4 className="report-section-heading font-mono">RISK ASSESSMENT & REASON</h4>
                <div className="report-subcard font-mono">
                  <div className="risk-summary-row">
                    <span>
                      Highest Risk Score: <strong>{report?.highest_risk_score || activeCampaign?.highest_risk_score || 0}</strong>
                    </span>
                    <span>
                      Average Risk Score: <strong>{report?.average_risk_score || activeCampaign?.average_risk_score || 0}</strong>
                    </span>
                    <span>
                      Target Category: <strong>{report?.target_categories?.join(', ') || 'Financial'}</strong>
                    </span>
                  </div>
                  <div className="escalation-reason-box">
                    <span className="reason-label">ESCALATION RATIONALE:</span>
                    <p className="reason-text">
                      {report?.escalation_reason ||
                        `Campaign contains ${activeCampaign?.incident_count || 3} linked HIGH/CRITICAL incidents and crossed the configured campaign escalation threshold.`}
                    </p>
                  </div>
                  {report?.integrity_hash && (
                    <div className="integrity-hash-row">
                      <span className="hash-label">INTEGRITY SHA-256:</span>
                      <span className="hash-val">{report.integrity_hash}</span>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="report-modal-footer">
              <span className="footer-privacy-guarantee font-mono">
                ✓ Zero transcripts • Zero audio • Zero victim PII stored
              </span>
              <button
                type="button"
                className="btn-modal-close font-mono"
                onClick={() => setIsReportModalOpen(false)}
              >
                CLOSE DOSSIER
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
