import React from 'react'
import { Shield, Radio, Activity, Cpu, Mic, FileText } from 'lucide-react'

export default function Header({
  connectionStatus,
  mode,
  isListening = false,
  isSimulating = false,
  hasIncidentData = false,
  onOpenIncidentSummary = null,
}) {
  const getConnectionConfig = () => {
    switch (connectionStatus) {
      case 'connected':
        return { label: 'CORE WS CONNECTED', className: 'online' }
      case 'connecting':
        return { label: 'WS CONNECTING...', className: 'connecting' }
      case 'offline':
      default:
        return { label: 'WS OFFLINE', className: 'offline' }
    }
  }

  const getModeConfig = () => {
    if (isListening) {
      return {
        label: 'BROWSER MIC DEMO · LOCAL WEB SPEECH',
        className: 'mode-mic',
        icon: Mic,
        title: 'Microphone audio routed locally via browser Web Speech API (offline)',
      }
    }
    if (isSimulating || mode === 'SIMULATION') {
      return {
        label: 'SIMULATION · MOCK STT',
        className: 'mode-sim',
        icon: Cpu,
        title: 'Deterministic multi-turn scam scenario running through local mock STT',
      }
    }
    if (mode === 'LIVE_CALL') {
      return {
        label: 'LIVE CARRIER · TWILIO / DEEPGRAM',
        className: 'mode-live',
        icon: Radio,
        title: 'Real-time carrier telephony monitored via Twilio Media Stream & Deepgram STT',
      }
    }
    return {
      label: 'STANDBY · LOCAL TESTBENCH',
      className: 'mode-standby',
      icon: Activity,
      title: 'Standby mode — ready for simulation, browser mic, or manual injection',
    }
  }

  const getPrivacyConfig = () => {
    if (isSimulating || mode === 'SIMULATION') {
      return {
        label: 'SIMULATION · NO MIC',
        className: 'privacy-sim',
        dotColor: '#38bdf8',
        title: 'Simulation scenario active: No local microphone audio',
      }
    }
    if (isListening) {
      return {
        label: 'MIC ACTIVE',
        className: 'privacy-mic-active',
        dotColor: '#10b981',
        title: 'Browser microphone active: Capturing local voice via Web Speech API',
      }
    }
    if (mode === 'LIVE_CALL') {
      return {
        label: 'LIVE CARRIER · MONITORING',
        className: 'privacy-carrier',
        dotColor: '#06b6d4',
        title: 'Monitored telephony call via Twilio carrier media stream',
      }
    }
    return {
      label: 'MIC OFF',
      className: 'privacy-mic-off',
      dotColor: '#64748b',
      title: 'Microphone is inactive. Channel is idle.',
    }
  }

  const conn = getConnectionConfig()
  const modeConfig = getModeConfig()
  const privacy = getPrivacyConfig()
  const ModeIcon = modeConfig.icon

  return (
    <header className="glass-panel header">
      <div className="brand">
        <div className="brand-icon">
          <Shield size={20} />
        </div>
        <div>
          <div className="brand-title-row">
            <h1 className="brand-title">RAKSHA</h1>
            <span className="brand-version-badge font-mono">v0.1.0 SOC</span>
          </div>
          <p className="brand-subtitle">Real-Time Scam Call Interception & Caregiver Defense</p>
        </div>
      </div>

      <div className="header-badges">
        {/* Explicit Privacy Audio Source Indicator */}
        <div className={`privacy-badge ${privacy.className}`} title={privacy.title}>
          <span className="privacy-status-dot" style={{ backgroundColor: privacy.dotColor }} />
          <span className="font-mono">{privacy.label}</span>
        </div>

        {/* Mode Indicator with explicit provider/engine clarity */}
        <div className={`mode-badge ${modeConfig.className}`} title={modeConfig.title}>
          <ModeIcon size={13} className="mode-icon" />
          <span className="font-mono">{modeConfig.label}</span>
        </div>

        {/* WebSocket Connection Status */}
        <div className={`status-badge ${conn.className}`} title={`Connection Status: ${conn.label}`}>
          <span className="pulse-dot" />
          <span className="font-mono">{conn.label}</span>
        </div>

        {/* Incident Summary Quick Access Button */}
        {hasIncidentData && onOpenIncidentSummary && (
          <button
            type="button"
            className="btn-header-summary"
            onClick={onOpenIncidentSummary}
            title="Open comprehensive incident report for this session"
          >
            <FileText size={13} />
            <span>Incident Report</span>
          </button>
        )}
      </div>
    </header>
  )
}
