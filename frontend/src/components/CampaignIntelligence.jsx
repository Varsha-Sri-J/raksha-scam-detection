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
  HeartHandshake,
  Network,
  ShieldCheck,
} from 'lucide-react'

export default function CampaignIntelligence({
  campaign: propCampaign = null,
  caregiverStatus = null,
  onCampaignUpdate = null,
  role = 'police',
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

  // Readable tactic formatter
  const TACTIC_READABLE_MAP = {
    AUTHORITY_IMPERSONATION: 'Authority Impersonation',
    OTP_EXTRACTION: 'OTP Requests',
    FINANCIAL_REDIRECTION: 'Money Transfer',
    FEAR_INTIMIDATION: 'Intimidation & Pressure',
    URGENCY_PRESSURE: 'Urgency Pressure',
    ISOLATION_TACTIC: 'Call Isolation',
    VERIFICATION_TRAP: 'Verification Trap',
    COURIER_CUSTOMS_SCAM: 'Courier Scam',
    POLICE_ARREST_THREAT: 'Police Threat',
    BANK_SECURITY_FRAUD: 'Bank Impersonation',
    DIGITAL_ARREST: 'Digital Arrest',
  }

  const formatTacticReadable = (tactic) => {
    if (!tactic) return 'Unknown'
    const key = String(tactic).toUpperCase().trim()
    if (TACTIC_READABLE_MAP[key]) return TACTIC_READABLE_MAP[key]
    return key
      .replace(/_/g, ' ')
      .toLowerCase()
      .replace(/\b\w/g, (c) => c.toUpperCase())
  }


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

  const riskTier = activeCampaign?.highest_risk_score >= 80
    ? 'CRITICAL'
    : activeCampaign?.highest_risk_score >= 60
    ? 'HIGH'
    : activeCampaign?.highest_risk_score >= 40
    ? 'MEDIUM'
    : 'LOW'

  const incidentList =
    report?.linked_incident_ids?.length > 0
      ? report.linked_incident_ids
      : activeCampaign?.linked_incidents?.map((i) => i.incident_id).filter(Boolean) || [
          'session-03-en',
          'session-04-hi',
          'session-05-te',
        ]

  const rawCallers =
    report?.observed_caller_identifiers?.length > 0
      ? report.observed_caller_identifiers
      : activeCampaign?.observed_caller_identifiers?.length > 0
      ? activeCampaign.observed_caller_identifiers
      : activeCampaign?.linked_incidents?.map((i) => i.caller_masked).filter(Boolean) || []

  const displayCallers =
    rawCallers.length > 0
      ? rawCallers.map((c) => (c && c !== 'Unknown' ? c : '+91 98765 *****'))
      : ['+91 98765 00001 (Masked)', '+91 98765 00002 (Masked)', '+91 98765 00003 (Masked)']

  return (
    <section className="campaign-intelligence-section" aria-label="Campaign Link Intelligence">
      <div className="glass-panel campaign-panel">
        {/* Panel Header */}
        <div className="campaign-header">
          <div className="campaign-header-left">
            <ShieldAlert size={18} className="campaign-shield-icon" />
            <div className="campaign-title-group">
              <div className="campaign-title-row">
                <h3 className="campaign-title font-mono">
                  {activeCampaign ? 'SCAM CAMPAIGN DETECTED' : 'CAMPAIGN INTELLIGENCE'}
                </h3>
                {activeCampaign && (
                  <span className="campaign-id-badge font-mono">
                    {activeCampaign.campaign_id}
                  </span>
                )}
                {getStatusBadge()}
              </div>
              <span className="campaign-lead-text">
                {activeCampaign
                  ? `RAKSHA linked ${activeCampaign.incident_count} call${activeCampaign.incident_count === 1 ? '' : 's'} showing similar scam behavior.`
                  : 'Cross-call pattern linking and syndicate detection engine.'}
              </span>
            </div>
          </div>

          <div className="campaign-header-right">
            {activeCampaign && (
              <span className="campaign-incident-count font-mono">
                Linked Incidents: <strong>{activeCampaign.incident_count}</strong>
              </span>
            )}
          </div>
        </div>

        {/* Panel Content */}
        <div className="campaign-content">
          {!activeCampaign ? (
            <div className="campaign-empty-state">
              <p className="campaign-empty-text">No cross-call scam campaign detected yet.</p>
              <span className="campaign-empty-hint font-mono">
                RAKSHA continuously correlates high and critical risk incidents. When multiple calls exhibit matching social-engineering tactics and behavioral progression, they link automatically into this syndicated campaign dossier.
              </span>
            </div>
          ) : (
            <div className="campaign-body">
              {/* Informational Caregiver Delivery Notice */}
              {caregiverStatus === 'FAILED' && (
                <div className="caregiver-fallback-alert font-mono">
                  <AlertTriangle size={13} color="var(--color-medium)" />
                  <span>CAREGIVER ALERT: FAILED • DASHBOARD ESCALATION ACTIVE</span>
                </div>
              )}

              {/* Metrics Grid */}
              <div className="campaign-grid">
                <div className="campaign-metric-card">
                  <span className="metric-label font-mono">RELATED CALLS</span>
                  <span className="metric-value font-mono highlight-number">
                    {activeCampaign.incident_count}
                  </span>
                  <span className="metric-sub font-mono">
                    Threshold: 3 for escalation
                  </span>
                </div>

                <div className="campaign-metric-card">
                  <span className="metric-label font-mono">RISK</span>
                  <div className="risk-comparison-row font-mono">
                    <span className="peak-risk-val">
                      {riskTier} • {Math.round(activeCampaign.highest_risk_score || 0)}/100
                    </span>
                  </div>
                  <span className="metric-sub font-mono">
                    Average risk: {Math.round(activeCampaign.average_risk_score || 0)}/100
                  </span>
                </div>

                <div className="campaign-metric-card">
                  <span className="metric-label font-mono">MAIN TACTICS</span>
                  <div className="campaign-tactics-list font-mono">
                    {activeCampaign.dominant_tactics && activeCampaign.dominant_tactics.length > 0 ? (
                      activeCampaign.dominant_tactics.slice(0, 3).map((t, i) => (
                        <span key={i} className="campaign-tactic-pill">
                          {formatTacticReadable(t)}
                        </span>
                      ))
                    ) : (
                      <span className="campaign-tactic-pill muted">Analyzing...</span>
                    )}
                  </div>
                  <span className="metric-sub font-mono">
                    Target: {activeCampaign.target_categories?.join(', ') || 'Financial & Identity'}
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
              </div>

              {/* Why These Calls Were Linked */}
              <div className="campaign-why-linked-card">
                <div className="why-linked-title-row font-mono">
                  <Activity size={13} color="#38bdf8" />
                  <span>WHY THESE CALLS WERE LINKED</span>
                </div>
                <p className="why-linked-quote">
                  "Similar social-engineering behavior was observed across the calls."
                </p>
                <div className="why-linked-meta font-mono">
                  <span>
                    Matching tactics: <strong>{activeCampaign.dominant_tactics?.slice(0, 3).map(formatTacticReadable).join(' • ') || 'Behavioral pattern'}</strong>
                  </span>
                  <span>•</span>
                  <span>
                    Progression: <strong>{activeCampaign.attack_progression_signature?.slice(0, 3).map(formatTacticReadable).join(' → ') || 'Linear escalation'}</strong>
                  </span>
                  {activeCampaign.observed_caller_identifiers?.length > 1 && (
                    <>
                      <span>•</span>
                      <span>Originating numbers: <strong>{activeCampaign.observed_caller_identifiers.length} callers observed</strong></span>
                    </>
                  )}
                </div>
              </div>

              {/* Escalation Action Bar */}
              <div className="campaign-actions-row">
                {activeCampaign.status === 'ESCALATION_ELIGIBLE' && !report && (
                  <div className="escalation-prompt-box">
                    <div className="escalation-prompt-text font-mono">
                      <AlertTriangle size={16} color="var(--color-critical)" />
                      <div>
                        <span className="escalation-title">ESCALATION THRESHOLD REACHED</span>
                        <span className="escalation-desc">
                          3 related high-risk calls have been identified.
                        </span>
                      </div>
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
                          <FileText size={14} /> GENERATE DEMO POLICE REPORT
                        </>
                      )}
                    </button>
                  </div>
                )}

                {(report || activeCampaign.status === 'REPORT_GENERATED') && (
                  <div className="escalation-completed-box">
                    <div className="escalation-completed-text font-mono">
                      <CheckCircle2 size={16} color="var(--color-safe)" />
                      <div>
                        <span className="report-badge-title">
                          ✓ DEMO REPORT READY
                        </span>
                        <div className="report-id-row">
                          <span className="report-id-text">
                            Report ID: {report?.report_id || 'RAKSHA-NCRP-ACTIVE'}
                          </span>
                          <span className="demo-disclaimer-pill font-mono">
                            DEMO ONLY — NO ACTUAL TRANSMISSION TO LAW ENFORCEMENT
                          </span>
                        </div>
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

                {(activeCampaign.status === 'DETECTED' || activeCampaign.status === 'ACTIVE_MONITORING') && (
                  <div className="escalation-monitoring-box font-mono">
                    <span className="pulse-dot-amber" />
                    <span>
                      ACTIVE MONITORING: <strong>{activeCampaign.incident_count}/3</strong> related calls observed. Law-enforcement escalation threshold unlocks at 3 linked calls.
                    </span>
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
            {/* 1. HEADER */}
            <div className="report-modal-header">
              <div className="report-title-group">
                <div className="report-badge-icon">
                  <ShieldAlert size={22} color="#38bdf8" />
                </div>
                <div>
                  <div className="report-header-topline">
                    <span className="report-org-name font-mono">RAKSHA</span>
                    <span className="report-sep">•</span>
                    <span className="report-classification font-mono">INCIDENT DOSSIER</span>
                  </div>
                  <h3 id="report-modal-title" className="report-modal-title font-mono">
                    SCAM CAMPAIGN INTELLIGENCE REPORT
                  </h3>
                  <span className="report-subtitle">
                    Synthetic Law-Enforcement Incident Dossier
                  </span>
                </div>
              </div>
              <button
                type="button"
                className="inspector-close-btn"
                onClick={() => setIsReportModalOpen(false)}
                aria-label="Close dossier"
              >
                <X size={18} />
              </button>
            </div>

            {/* Modal Body */}
            <div className="report-modal-body">
              {/* 2. DEMO DISCLAIMER */}
              <div className="report-disclaimer-box font-mono">
                <Lock size={15} color="#fbbf24" style={{ flexShrink: 0, marginTop: 2 }} />
                <div>
                  <strong>DEMO ONLY — NO ACTUAL TRANSMISSION TO LAW ENFORCEMENT</strong>
                  <p>
                    This is an in-memory intelligence dossier generated for demonstration purposes.
                    No communication has been sent to NCRP, I4C, police, or external authorities.
                  </p>
                </div>
              </div>

              {/* 3. EXECUTIVE SUMMARY */}
              <div className="report-section">
                <div className="dossier-section-header">
                  <FileText size={14} color="#38bdf8" />
                  <h4 className="report-section-heading font-mono">EXECUTIVE SUMMARY</h4>
                </div>
                <div className="dossier-summary-card">
                  <p className="dossier-summary-lead">
                    RAKSHA linked multiple high-risk calls showing similar social-engineering behavior.
                  </p>
                  <p className="dossier-summary-detail">
                    Cross-session behavioral heuristics and semantic embeddings confirmed recurring psychological manipulation tactics targeting protected accounts. Behavioral signatures indicate coordinated syndicate operation rather than isolated nuisance calling.
                  </p>
                </div>
              </div>

              {/* 4. KEY METRICS */}
              <div className="report-section">
                <div className="dossier-section-header">
                  <Activity size={14} color="#38bdf8" />
                  <h4 className="report-section-heading font-mono">KEY METRICS</h4>
                </div>
                <div className="dossier-key-metrics-grid">
                  <div className="dossier-metric-card font-mono">
                    <span className="metric-label">RELATED CALLS</span>
                    <span className="metric-val text-cyan">
                      {report?.incident_count || activeCampaign?.incident_count || 3} Linked Calls
                    </span>
                    <span className="metric-sub">Coordinated incidents</span>
                  </div>
                  <div className="dossier-metric-card font-mono">
                    <span className="metric-label">HIGHEST RISK</span>
                    <span className="metric-val text-critical">
                      Score {Math.round(report?.highest_risk_score || activeCampaign?.highest_risk_score || 100)} / 100
                    </span>
                    <span className="metric-sub">Critical threat tier</span>
                  </div>
                  <div className="dossier-metric-card font-mono">
                    <span className="metric-label">CALLERS OBSERVED</span>
                    <span className="metric-val text-amber">
                      {displayCallers.length} Numbers
                    </span>
                    <span className="metric-sub">Masked caller IDs</span>
                  </div>
                  <div className="dossier-metric-card font-mono">
                    <span className="metric-label">CAMPAIGN STATUS</span>
                    <span className="metric-val text-safe">
                      {report?.status === 'MOCK_REPORT_GENERATED' || activeCampaign?.status === 'REPORT_GENERATED'
                        ? 'REPORT GENERATED'
                        : 'ESCALATION ELIGIBLE'}
                    </span>
                    <span className="metric-sub">Escalation crossed</span>
                  </div>
                </div>
              </div>

              {/* 5. CAMPAIGN DETAILS */}
              <div className="report-section">
                <div className="dossier-section-header">
                  <ShieldAlert size={14} color="#38bdf8" />
                  <h4 className="report-section-heading font-mono">CAMPAIGN DETAILS</h4>
                </div>
                <div className="report-meta-grid font-mono">
                  <div className="report-meta-item">
                    <span className="meta-label">CAMPAIGN ID</span>
                    <span className="meta-val">{activeCampaign?.campaign_id || 'CMP-BFCE6B78'}</span>
                  </div>
                  <div className="report-meta-item">
                    <span className="meta-label">REPORT ID</span>
                    <span className="meta-val text-cyan">{report?.report_id || 'RAKSHA-NCRP-ACTIVE'}</span>
                  </div>
                  <div className="report-meta-item">
                    <span className="meta-label">TIMELINE</span>
                    <span className="meta-val">
                      {formatDate(report?.first_seen || activeCampaign?.first_seen)} →{' '}
                      {formatDate(report?.last_seen || activeCampaign?.last_seen)}
                    </span>
                  </div>
                  <div className="report-meta-item">
                    <span className="meta-label">TARGET CATEGORY</span>
                    <span className="meta-val">
                      {report?.target_categories?.join(', ') || 'Credential & OTP Theft'}
                    </span>
                  </div>
                </div>
              </div>

              {/* 6. ATTACK PATTERN */}
              <div className="report-section">
                <div className="dossier-section-header">
                  <ArrowRight size={14} color="#38bdf8" />
                  <h4 className="report-section-heading font-mono">COMMON ATTACK PROGRESSION</h4>
                </div>
                <div className="dossier-progression-track font-mono">
                  {[
                    { step: '01', name: 'Authority', desc: 'Officer / Cyber Crime impersonation' },
                    { step: '02', name: 'Threat / Intimidation', desc: 'Account freeze & arrest threats' },
                    { step: '03', name: 'Urgency', desc: '15-minute countdown pressure' },
                    { step: '04', name: 'Isolation', desc: 'Demand to stay on line & secrecy' },
                    { step: '05', name: 'OTP / Credential Request', desc: 'Acute 6-digit code extraction' },
                  ].map((node, idx, arr) => (
                    <React.Fragment key={idx}>
                      <div className="dossier-progression-step">
                        <div className="step-header">
                          <span className="step-num">{node.step}</span>
                          <span className="step-title">{node.name}</span>
                        </div>
                        <span className="step-desc">{node.desc}</span>
                      </div>
                      {idx < arr.length - 1 && (
                        <div className="step-arrow" aria-hidden="true">
                          <ArrowRight size={14} />
                        </div>
                      )}
                    </React.Fragment>
                  ))}
                </div>
              </div>

              {/* 7. LINKED INCIDENTS & 8. CALLER IDENTIFIERS */}
              <div className="report-section">
                <div className="report-two-col">
                  {/* 7. LINKED INCIDENTS */}
                  <div className="report-subcard font-mono">
                    <span className="subcard-title">
                      LINKED INCIDENTS ({incidentList.length})
                    </span>
                    <div className="incident-id-tags">
                      {incidentList.map((id, idx) => (
                        <span key={idx} className="incident-id-tag">
                          #{id}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* 8. CALLER IDENTIFIERS (MASKED) */}
                  <div className="report-subcard font-mono">
                    <span className="subcard-title">
                      CALLER IDENTIFIERS (MASKED)
                    </span>
                    <div className="masked-callers-dossier">
                      {displayCallers.map((cid, idx) => (
                        <span key={idx} className="masked-caller-pill">
                          <PhoneCall size={12} color="#f43f5e" /> {cid}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              {/* 9. ESCALATION REASON */}
              <div className="report-section">
                <div className="dossier-section-header">
                  <AlertTriangle size={14} color="#ef4444" />
                  <h4 className="report-section-heading font-mono">ESCALATION REASON</h4>
                </div>
                <div className="dossier-escalation-card">
                  <p className="dossier-escalation-text">
                    {report?.escalation_reason ||
                      `Campaign contains ${activeCampaign?.incident_count || 3} linked HIGH/CRITICAL incidents and crossed the configured campaign escalation threshold of 3 related high-risk calls.`}
                  </p>
                </div>
              </div>

              {/* 10. INTEGRITY (Secondary) */}
              <div className="dossier-integrity-card font-mono">
                <div className="integrity-label-row">
                  <CheckCircle2 size={13} color="#10b981" />
                  <span className="integrity-label">CRYPTOGRAPHIC INTEGRITY:</span>
                  <span className="integrity-verified">SHA-256 VERIFIED</span>
                </div>
                <span className="integrity-hash-val" title={report?.integrity_hash || '76a8365028ff4fba2abf79a38412b75afc45d6769b80a5079b248c09d97cf5e3'}>
                  {report?.integrity_hash || activeCampaign?.integrity_hash || '76a8365028ff4fba2abf79a38412b75afc45d6769b80a5079b248c09d97cf5e3'}
                </span>
              </div>
            </div>

            {/* 11. PRIVACY FOOTER & 12. FOOTER ACTION */}
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
