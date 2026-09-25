import React from 'react'

/**
 * CinematicBackground Component
 * High-end organic liquid-metal engine powered by local inline SVG filters.
 * Molten silver, soft studio highlights, and graphite liquid flowing through a black environment.
 * Zero external assets, zero remote URLs, pure hardware-accelerated local SVG.
 */
export default function CinematicBackground({ riskTier = 'SAFE' }) {
  const isCritical = riskTier === 'CRITICAL'
  const isHigh = riskTier === 'HIGH'

  return (
    <div
      className={`cinematic-liquid-metal ${isCritical ? 'is-critical' : isHigh ? 'is-high' : ''}`}
      aria-hidden="true"
    >
      {/* 1. Dynamic Local SVG Molten Liquid Field */}
      <svg
        className="liquid-metal-svg"
        viewBox="0 0 1600 1000"
        preserveAspectRatio="xMidYMid slice"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          {/* Liquid Distortion Filter with continuous organic turbulence */}
          <filter
            id="liquid-distortion"
            x="-20%"
            y="-20%"
            width="140%"
            height="140%"
            colorInterpolationFilters="sRGB"
          >
            <feTurbulence
              type="fractalNoise"
              baseFrequency="0.0055 0.0035"
              numOctaves="4"
              seed="24"
              result="turbulence"
            >
              <animate
                attributeName="baseFrequency"
                dur="42s"
                values="0.005 0.003; 0.008 0.005; 0.006 0.0035; 0.005 0.003"
                repeatCount="indefinite"
              />
            </feTurbulence>
            <feDisplacementMap
              in="SourceGraphic"
              in2="turbulence"
              scale="75"
              xChannelSelector="R"
              yChannelSelector="G"
              result="displaced"
            />
            <feGaussianBlur in="displaced" stdDeviation="22" result="blurred" />
            <feSpecularLighting
              in="blurred"
              surfaceScale="5.5"
              specularConstant="1.3"
              specularExponent="20"
              lightingColor="#ffffff"
              result="specular"
            >
              <feDistantLight azimuth="220" elevation="45" />
            </feSpecularLighting>
            <feComposite in="specular" in2="blurred" operator="in" result="specular-composite" />
            <feMerge>
              <feMergeNode in="blurred" />
              <feMergeNode in="specular-composite" />
            </feMerge>
          </filter>

          {/* Monochromatic Liquid Gradients: Molten Silver, Studio White, Graphite */}
          <radialGradient id="liquidGrad1" cx="30%" cy="35%" r="65%">
            <stop offset="0%" stopColor="#8d95a6" stopOpacity="0.85" />
            <stop offset="35%" stopColor="#434958" stopOpacity="0.70" />
            <stop offset="70%" stopColor="#181a22" stopOpacity="0.45" />
            <stop offset="100%" stopColor="#000000" stopOpacity="0" />
          </radialGradient>

          <radialGradient id="liquidGrad2" cx="72%" cy="38%" r="60%">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0.90" />
            <stop offset="25%" stopColor="#d1d6e2" stopOpacity="0.78" />
            <stop offset="55%" stopColor="#656c7d" stopOpacity="0.55" />
            <stop offset="85%" stopColor="#1b1f28" stopOpacity="0.30" />
            <stop offset="100%" stopColor="#000000" stopOpacity="0" />
          </radialGradient>

          <radialGradient id="liquidGrad3" cx="45%" cy="75%" r="65%">
            <stop offset="0%" stopColor="#9ba3b5" stopOpacity="0.78" />
            <stop offset="40%" stopColor="#4a5060" stopOpacity="0.62" />
            <stop offset="75%" stopColor="#1a1d25" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#000000" stopOpacity="0" />
          </radialGradient>

          <linearGradient id="sheenWaveGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#000000" stopOpacity="0" />
            <stop offset="25%" stopColor="#ffffff" stopOpacity="0.25" />
            <stop offset="50%" stopColor="#ffffff" stopOpacity="0.75" />
            <stop offset="72%" stopColor="#cdd3de" stopOpacity="0.45" />
            <stop offset="100%" stopColor="#000000" stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* Base Pure Dark Charcoal Void */}
        <rect width="100%" height="100%" fill="#030406" />

        {/* Filter-Displaced Molten Liquid Shapes */}
        <g filter="url(#liquid-distortion)">
          {/* Shape 1: Graphite Deep Swell */}
          <path
            className="liquid-shape liquid-shape-1"
            d="M -100 150 Q 300 -100 800 200 T 1700 100 L 1750 900 Q 1100 1100 600 850 T -100 800 Z"
            fill="url(#liquidGrad1)"
          />

          {/* Shape 2: Molten Silver Crest */}
          <ellipse
            className="liquid-shape liquid-shape-2"
            cx="1060"
            cy="360"
            rx="590"
            ry="430"
            fill="url(#liquidGrad2)"
          />

          {/* Shape 3: Counter-flow Wave */}
          <path
            className="liquid-shape liquid-shape-3"
            d="M -150 500 Q 400 300 900 650 T 1750 600 L 1750 1100 L -150 1100 Z"
            fill="url(#liquidGrad3)"
          />

          {/* Shape 4: Luminous Sheen Travel Wave */}
          <path
            className="liquid-shape liquid-sheen"
            d="M -200 450 Q 500 150 1100 550 T 1800 400 L 1800 750 Q 1100 500 500 850 T -200 700 Z"
            fill="url(#sheenWaveGrad)"
            opacity="0.85"
          />
        </g>
      </svg>

      {/* Subtle edge perimeter vignette — keeps center completely open and liquid visible */}
      <div className="liquid-edge-vignette" />

      {/* Optional critical perimeter atmosphere only */}
      {isCritical && <div className="liquid-critical-edge-glow" />}
    </div>
  )
}
