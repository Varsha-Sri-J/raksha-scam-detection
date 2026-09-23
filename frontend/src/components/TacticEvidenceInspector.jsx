import React from 'react'
import { X, ShieldAlert, CheckCircle2, Clock, FileText, Sparkles } from 'lucide-react'

export default function TacticEvidenceInspector({ tactic, onClose }) {
  if (!tactic) return null

  const timeString = tactic.timestamp
    ? new Date(
        typeof tactic.timestamp === 'number' && tactic.timestamp < 1e12
          ? tactic.timestamp * 1000
          : tactic.timestamp
      ).toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    : null

  return (
    <div className="inspector-overlay" onClick={onClose}>
      <div
        className="glass-panel inspector-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="inspector-title"
      >
        <div className="inspector-header">
          <div className="inspector-title-group">
            <ShieldAlert size={18} color="var(--accent-rose)" />
            <div>
              <h3 id="inspector-title" className="inspector-title">
                {tactic.name}
              </h3>
              <span className="inspector-canonical-id font-mono">
                {tactic.canonicalId || tactic.id}
              </span>
            </div>
          </div>
          <button
            type="button"
            className="inspector-close-btn"
            onClick={onClose}
            aria-label="Close evidence inspector"
          >
            <X size={18} />
          </button>
        </div>

        <div className="inspector-body">
          {/* Confidence & Severity Header */}
          <div className="inspector-meta-row">
            <div className="inspector-meta-chip">
              <span className="chip-label">Confidence</span>
              <span className="chip-value confidence-value">
                {tactic.confidence !== null && tactic.confidence !== undefined
                  ? `${tactic.confidence}%`
                  : 'Confirmed'}
              </span>
            </div>

            <div className="inspector-meta-chip">
              <span className="chip-label">Weight</span>
              <span className="chip-value">{tactic.weight || '80%'}</span>
            </div>

            {timeString && (
              <div className="inspector-meta-chip">
                <span className="chip-label">Detected At</span>
                <span className="chip-value font-mono">
                  <Clock size={11} style={{ marginRight: 4 }} />
                  {timeString}
                </span>
              </div>
            )}
          </div>

          {/* Psychological Definition */}
          <div className="inspector-section">
            <div className="section-label">
              <Sparkles size={13} color="var(--accent-cyan)" />
              <span>Psychological Exploitation Mechanism</span>
            </div>
            <p className="inspector-desc-text">{tactic.desc}</p>
          </div>

          {/* Verbatim Evidence Snippet */}
          <div className="inspector-section">
            <div className="section-label">
              <FileText size={13} color="var(--accent-rose)" />
              <span>Verbatim Evidence in Audio Stream</span>
            </div>
            <div className="evidence-quote-box">
              {tactic.evidence ? (
                <blockquote className="verbatim-quote">
                  "{tactic.evidence}"
                </blockquote>
              ) : (
                <p className="no-evidence-text">
                  Pattern identified through aggregated utterance semantics across current call session.
                </p>
              )}
            </div>
          </div>

          {/* Associated Full Utterance if different */}
          {tactic.utterance && tactic.utterance !== tactic.evidence && (
            <div className="inspector-section">
              <div className="section-label">
                <span>Associated Call Utterance</span>
              </div>
              <div className="utterance-context-box">
                <span className="font-mono">{tactic.utterance}</span>
              </div>
            </div>
          )}
        </div>

        <div className="inspector-footer">
          <span className="inspector-footnote">
            Evidence derived strictly from streaming STT and semantic classifier pipeline.
          </span>
          <button type="button" className="btn-inspector-done" onClick={onClose}>
            Done
          </button>
        </div>
      </div>
    </div>
  )
}
