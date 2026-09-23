import React from 'react'
import { Shield, Radio, Activity, Cpu } from 'lucide-react'

export default function Header({ connectionStatus, mode }) {
  // connectionStatus: 'connected' | 'connecting' | 'offline'
  // mode: 'LIVE_CALL' | 'SIMULATION' | 'STANDBY'

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
    switch (mode) {
      case 'LIVE_CALL':
        return { label: 'LIVE CALL ACTIVE', className: 'mode-live', icon: Radio }
      case 'SIMULATION':
        return { label: 'SIMULATION MODE', className: 'mode-sim', icon: Cpu }
      case 'STANDBY':
      default:
        return { label: 'STANDBY / MONITORING', className: 'mode-standby', icon: Activity }
    }
  }

  const conn = getConnectionConfig()
  const modeConfig = getModeConfig()
  const ModeIcon = modeConfig.icon

  return (
    <header className="glass-panel header">
      <div className="brand">
        <div className="brand-icon">
          <Shield size={22} />
        </div>
        <div>
          <h1 className="brand-title">RAKSHA</h1>
          <p className="brand-subtitle">Real-Time Scam Call Protection</p>
        </div>
      </div>

      <div className="header-badges">
        {/* Mode Indicator */}
        <div className={`mode-badge ${modeConfig.className}`} title={`Operating Mode: ${modeConfig.label}`}>
          <ModeIcon size={14} className="mode-icon" />
          <span>{modeConfig.label}</span>
        </div>

        {/* WebSocket Connection Status */}
        <div className={`status-badge ${conn.className}`} title={`Connection Status: ${conn.label}`}>
          <span className="pulse-dot" />
          <span>{conn.label}</span>
        </div>
      </div>
    </header>
  )
}
