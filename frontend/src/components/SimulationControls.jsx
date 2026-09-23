import React, { useState } from 'react'
import { Send, RefreshCw, RotateCcw, Terminal } from 'lucide-react'

export default function SimulationControls({
  onSimulate,
  onResetSession,
  onSendTranscript,
  isSimulating = false,
  disabled = false,
}) {
  const [inputText, setInputText] = useState('')
  const [speaker, setSpeaker] = useState('CALLER')

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!inputText.trim()) return

    onSendTranscript({
      speaker,
      text: inputText.trim(),
    })
    setInputText('')
  }

  return (
    <div className="simulation-controls-wrapper">
      <div className="simulation-banner-header">
        <div className="simulation-title-group">
          <Terminal size={14} color="var(--accent-amber)" />
          <span className="simulation-title">Test & Simulation Suite</span>
        </div>
        <span className="simulation-env-tag">
          Local Mock STT & Pipeline Injection
        </span>
      </div>

      <div className="simulation-actions-bar">
        {/* Run Scam Simulation Button */}
        <button
          type="button"
          className="btn-simulate-scam"
          onClick={onSimulate}
          disabled={isSimulating || disabled}
          title="Run 5-step mock scam scenario through the RAKSHA streaming pipeline"
        >
          <RefreshCw
            size={14}
            className={isSimulating ? 'simulate-icon spinning' : 'simulate-icon'}
          />
          <span>{isSimulating ? 'Streaming Simulation...' : 'Simulate Scam Scenario'}</span>
        </button>

        {/* Reset Demo / New Session Button */}
        <button
          type="button"
          className="btn-reset-session"
          onClick={onResetSession}
          disabled={isSimulating}
          title="Start a fresh demo session with a new unique session ID"
        >
          <RotateCcw size={13} />
          <span>New Session</span>
        </button>

        {/* Manual Utterance Injection Form */}
        <form className="manual-inject-form" onSubmit={handleSubmit}>
          <select
            className="speaker-dropdown"
            value={speaker}
            onChange={(e) => setSpeaker(e.target.value)}
            disabled={isSimulating || disabled}
            aria-label="Speaker identity"
          >
            <option value="CALLER">Caller (Inbound Scammer)</option>
            <option value="CALLEE">Callee (Protected Senior)</option>
          </select>

          <input
            type="text"
            className="utterance-input"
            placeholder="Inject test utterance (e.g. 'This is officer Miller, give me your 6-digit code')..."
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            disabled={isSimulating || disabled}
          />

          <button
            type="submit"
            className="btn-inject-send"
            disabled={isSimulating || disabled || !inputText.trim()}
          >
            <Send size={13} />
            <span>Inject</span>
          </button>
        </form>
      </div>
    </div>
  )
}
