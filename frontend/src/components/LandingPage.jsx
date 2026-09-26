import React from 'react'
import { Shield, ShieldCheck, ShieldAlert, ArrowRight } from 'lucide-react'

const ROLES = [
  {
    id: 'user_caregiver',
    name: 'USER / CAREGIVER',
    description: 'Protect the person and monitor the call.',
    icon: ShieldCheck,
    color: '#10b981',
    accentBg: 'rgba(16, 185, 129, 0.12)',
    accentBorder: 'rgba(16, 185, 129, 0.35)',
  },
  {
    id: 'police',
    name: 'POLICE',
    description: 'Investigate linked scam campaigns.',
    icon: ShieldAlert,
    color: '#38bdf8',
    accentBg: 'rgba(56, 189, 248, 0.12)',
    accentBorder: 'rgba(56, 189, 248, 0.35)',
  },
]

export default function LandingPage({ onSelectRole }) {
  return (
    <div className="landing-page-wrapper">
      <div className="landing-page-content">
        {/* Top Brand Hero */}
        <div className="landing-hero">
          <div className="landing-logo-container">
            <div className="landing-shield-glow">
              <Shield size={36} color="#ffffff" />
            </div>
          </div>
          <h1 className="landing-title">RAKSHA</h1>
          <h2 className="landing-subtitle">Real-Time Scam Call Protection</h2>
          <p className="landing-tagline">
            Protecting people. Detecting scams. Connecting the right help.
          </p>
        </div>

        {/* 2 Role Options */}
        <div className="landing-roles-grid" role="region" aria-label="Select Role">
          {ROLES.map((role) => {
            const Icon = role.icon
            return (
              <button
                key={role.id}
                type="button"
                className="role-card glass-panel"
                onClick={() => onSelectRole(role.id)}
                aria-label={`Enter as ${role.name}`}
              >
                <div className="role-card-header">
                  <div
                    className="role-icon-box"
                    style={{
                      background: role.accentBg,
                      borderColor: role.accentBorder,
                      color: role.color,
                    }}
                  >
                    <Icon size={24} />
                  </div>
                  <span className="role-enter-pill font-mono">
                    SELECT ROLE <ArrowRight size={12} />
                  </span>
                </div>

                <div className="role-card-body">
                  <h3 className="role-name font-mono">{role.name}</h3>
                  <p className="role-description">{role.description}</p>
                </div>
              </button>
            )
          })}
        </div>

        {/* Minimal Footer */}
        <div className="landing-footer font-mono">
          <span>RAKSHA SCAM DEFENSE PLATFORM • CHOOSE A ROLE TO BEGIN</span>
        </div>
      </div>
    </div>
  )
}
