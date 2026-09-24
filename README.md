# RAKSHA: Real-Time Scam & Manipulation Detection Engine

RAKSHA ("Protection") is a real-time AI-assisted scam-call detection and protection platform designed to detect conversational manipulation and progressively respond to suspicious phone calls. Operating on live call transcripts, RAKSHA identifies coercive social engineering patterns, calculates a dynamic risk escalation score, and triggers deterministic downstream protections—including caregiver SMS alerts, in-call audio advisories, and carrier-level call severance.

---

## 1. Problem

Phone-based social engineering scams increasingly bypass traditional call screening. Legacy defenses rely primarily on static blocklists, known spam caller IDs, or malicious URLs. Modern fraudsters, however, weaponize **conversational psychological coercion**—manipulating vulnerable individuals (particularly the elderly) over multi-turn phone dialogues.

Single-keyword matching fails because attackers vary their phrasing, and isolated words like *"urgent"* or *"police"* occur frequently in legitimate emergencies. RAKSHA addresses this by evaluating conversational context across eight manipulation categories:

- **Authority Impersonation**: Falsely claiming to represent law enforcement, tax agencies, or financial fraud divisions.
- **Urgency & Time Pressure**: Imposing artificial, immediate deadlines to prevent rational deliberation.
- **Fear & Intimidation**: Threatening imminent arrest, frozen bank accounts, or legal prosecution.
- **Isolation & Secrecy**: Coercing the victim to remain on the line and conceal the conversation from family or bank staff.
- **Financial Redirection**: Instructing payment via atypical channels such as gift cards, wire transfers, or cryptocurrency kiosks.
- **Information & OTP Phishing**: Coercing the victim into revealing one-time passcodes (OTPs), PINs, or credentials.
- **Confusion & Cognitive Overload**: Overwhelming the listener with rapid legal/technical jargon to induce compliance.
- **False Salvation & Relief**: Offering a fabricated "safe account" or resolution once the victim complies.

Because scam victimization is cumulative, tracking **multi-turn context and co-occurring tactics** is essential to differentiate a high-pressure scam from a benign emergency.

---

## 2. Core Idea & Design Principles

RAKSHA runs an end-to-end streaming detection and response pipeline:

```
Audio / Transcript Stream
  ↓
Semantic Manipulation Classifier (Sentence Transformers)
  ↓
Dynamic Risk Engine (Severity, Repetition, Synergy, Safeguards)
  ↓
Protection Engine (Stateful Tier Decision)
  ↓
Downstream Protective Actions (Alerts, Caregiver SMS, Whisper Advisory, Line Severance)
  ↓
Real-Time Cyber Defense Dashboard (WebSocket Telemetry)
```

### Deterministic Downstream Policy
A central architectural decision in RAKSHA is the **separation of semantic detection from protective intervention**:
- Machine learning is used strictly for **semantic classification** (detecting whether an utterance reflects manipulation).
- All risk calculation, tier mapping, and protection actions follow **deterministic, auditable rule sets**.
- An LLM is **never** permitted to autonomously decide whether to alert a caregiver or sever a phone call. This guarantees zero hallucinated interventions, bounded execution latency (< 30ms), and predictable behavior.

---

## 3. Architecture

RAKSHA supports two operational topologies: an **Offline / Simulation Mode** (recommended for evaluation and demonstrations) and a **Live Telephony Boundary** (for carrier deployment).

### Offline / Demo Architecture (100% Local & Credential-Free)

```
┌───────────────────────────────────────────────────────────┐
│        Interactive Web Dashboard / Scenario Script        │
└─────────────────────────────┬─────────────────────────────┘
                              │ HTTP POST / WebSocket Inject
                              ▼
┌───────────────────────────────────────────────────────────┐
│                      Mock STT Provider                    │
│   (Generates structured, timed TranscriptSegments)        │
└─────────────────────────────┬─────────────────────────────┘
                              ▼
┌───────────────────────────────────────────────────────────┐
│              Streaming Pipeline Orchestrator              │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Semantic Classifier (all-MiniLM-L6-v2 Embeddings)   │  │
│  └──────────────────────────┬──────────────────────────┘  │
│                             ▼                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Dynamic Risk Engine (Synergy + Safeguard Rules)     │  │
│  └──────────────────────────┬──────────────────────────┘  │
│                             ▼                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Protection Engine (Cooldown & Escalation Policy)   │  │
│  └──────────────────────────┬──────────────────────────┘  │
│                             ▼                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Mock Downstream Providers                           │  │
│  │ (Audit logging: Caregiver SMS, Whisper, Disconnect) │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────┬─────────────────────────────┘
                              │ WebSocket Broadcast (/ws/call/{id})
                              ▼
┌───────────────────────────────────────────────────────────┐
│        React Cybersecurity Dashboard (Port 5173)          │
└───────────────────────────────────────────────────────────┘
```

### Live Telephony Architecture (External Ingress & Carrier Integration)

```
┌───────────────────────────────────────────────────────────┐
│                     Inbound PSTN Caller                   │
└─────────────────────────────┬─────────────────────────────┘
                              │ Twilio Voice Webhook
                              ▼
┌───────────────────────────────────────────────────────────┐
│             Twilio Dual-Leg Conference Bridge             │
│  ┌─────────────────────────┐   ┌────────────────────────┐ │
│  │ Inbound Scammer Leg     │   │ Protected Callee Leg   │ │
│  └─────────────────────────┘   └────────────────────────┘ │
└──────────────┬───────────────────────────────▲────────────┘
               │ Twilio Media Streams (x-mulaw)│ Injected TTS Whisper
               ▼                               │ / Call Leg Disconnect
┌──────────────────────────────────────────────┴────────────┐
│                    RAKSHA FastAPI Backend                 │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ TwilioDeepgramBridge → Deepgram Nova-2 (Live STT)   │  │
│  └──────────────────────────┬──────────────────────────┘  │
│                             ▼                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ StreamingPipeline → Classifier → Risk → Protection  │  │
│  └──────────────────────────┬──────────────────────────┘  │
│                             ▼                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Real Downstream Telephony Providers                 │  │
│  │ • Twilio REST API: Disconnect Scammer Leg           │  │
│  │ • Twilio Conference: Whisper Advisory to Callee     │  │
│  │ • Twilio Messaging API: Caregiver SMS Dispatch      │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────┬─────────────────────────────┘
                              │ WebSocket (/ws/call/{id})
                              ▼
┌───────────────────────────────────────────────────────────┐
│              Live Operator / React Dashboard              │
└───────────────────────────────────────────────────────────┘
```

*Note: The live integration boundary is implemented in code and verified via comprehensive integration tests. Running live carrier telephony requires active Twilio credentials, a Deepgram API key, and a public ingress tunnel.*

---

## 4. Detection Engine

The detection layer (`ai/classifier.py`) evaluates spoken utterances against RAKSHA's psychological taxonomy without relying on static keyword lists or external cloud LLMs:

- **Model**: Embedded local Sentence Transformer (`all-MiniLM-L6-v2`), running on CPU with ~25ms inference latency.
- **Tactic Anchors**: Each of the 8 manipulation categories is defined in `ai/tactics.py` with curated anchor phrases and formal descriptions. Anchor embeddings are precomputed and cached in memory at startup.
- **Cosine Similarity**: Incoming transcript segments are split into sentences, vectorized, and evaluated using cosine similarity against the anchor space:
  $$\text{sim}(u, a) = \frac{\mathbf{u} \cdot \mathbf{a}}{\|\mathbf{u}\| \|\mathbf{a}\|}$$
- **Threshold Matching**: Any match exceeding the calibrated similarity threshold of **`0.45`** triggers a `TacticMatch`.
- **Evidence Extraction**: The specific sentence yielding the maximum similarity is extracted as forensic evidence, paired with a calibrated confidence score.
- **Multi-Tactic Support**: An utterance expressing multiple tactics (e.g., *"I am Officer Davis, send $500 immediately or you will be arrested"*) yields multiple distinct `TacticMatch` events.

---

## 5. Dynamic Risk Engine

The Risk Engine (`backend/app/risk_engine.py`) consumes detected tactics over time and computes a bounded threat score between **`0.0`** and **`100.0`**:

1. **Base Tactic Scoring**:
   $$\text{Base} = 20.0 \times \text{severity\_weight} \times \text{confidence}$$
   Severity weights reflect real-world harm (e.g., `FINANCIAL_REDIRECTION` = 0.95, `AUTHORITY_IMPERSONATION` = 0.90, `URGENCY` = 0.75, `CONFUSION_OVERWHELM` = 0.65).
2. **Harmonic Repetition Bonus**:
   Repeated novel evidence for the same tactic increases score with diminishing returns:
   $$\text{Bonus} = \sum_{k=2}^{N} \frac{4.0}{k} \quad (\text{capped at } 12.0)$$
3. **Co-Occurrence Multipliers**:
   When diverse tactics combine, the multi-tactic multiplier escalates non-linearly:
   - 1 tactic: `1.0x`
   - 2 tactics: `1.15x`
   - 3 tactics: `1.35x`
   - 4 tactics: `1.50x`
   - 5+ tactics: `1.65x`
4. **Deterministic High-Danger Synergies**:
   Targeted bonuses reflect lethal psychological combinations:
   - *Authority + Fear*: `+8.0`
   - *Coercive Impending Arrest Triad* (Authority + Fear + Urgency): `+10.0`
   - *Financial Redirection / Phishing + Urgency or Fear*: `+12.0`
   - *Full Coercive Scam Nexus* ($\ge 4$ tactics including Authority & Financial): `+15.0`
5. **Legitimate Call Safeguards**:
   - **Isolated Urgency Cap**: If *only* Urgency is detected, the score is capped at **`22.0`** (`SAFE`).
   - **Isolated Authority Cap**: If *only* Authority Impersonation is detected, the score is capped at **`35.0`** (`LOW`).
6. **Risk Tiers (Actual Repository Thresholds)**:
   - **`SAFE`**: `0.0` to `< 25.0` (Normal conversation, no significant coercion)
   - **`LOW`**: `25.0` to `< 50.0` (Isolated urgency or mild indicators; monitored)
   - **`MEDIUM`**: `50.0` to `< 75.0` (Multiple indicators; advisory monitoring active)
   - **`HIGH`**: `75.0` to `< 90.0` (Coercive pattern detected; caregiver alert dispatched)
   - **`CRITICAL`**: `90.0` to `100.0` (Active financial/arrest extortion; emergency intervention triggered)

---

## 6. Protection Engine & Downstream Interventions

The Protection Engine (`backend/app/services/protection_engine.py`) translates the dynamic Risk Tier into stateful, rate-limited defense actions:

| Protection Level | Risk Tier | Downstream Actions Triggered |
| :--- | :--- | :--- |
| **`MONITORING`** | SAFE / LOW | Baseline state tracking; passive monitoring. |
| **`ADVISORY`** | MEDIUM | Heightened monitoring; downstream services primed. |
| **`WARNING`** | HIGH | Caregiver SMS Alert dispatched; In-Call Audio Whisper queued. |
| **`CRITICAL_INTERCEPT`** | CRITICAL | Emergency Telephony Line Severance; Priority UI Modal. |

### Downstream Capabilities
- **Dashboard Alerts**: Priority notification pushed instantly to the operator UI over WebSockets. Enforces a 20-second cooldown window to prevent operator alert fatigue, with immediate bypass on acute OTP or financial extraction tactics.
- **Caregiver SMS Notification** (`backend/app/services/notification_service.py`): Formats and sends an SMS to registered emergency family contacts with call details, detected tactics, and transcript summary.
- **Protected-User Warning** (`backend/app/services/user_warning_service.py`): Injects an audio advisory whisper directly into the callee's ear over the call conference leg.
- **Call Intervention / Disconnect** (`backend/app/services/intervention_service.py`): Executes carrier-level line severance on the scammer's call leg while maintaining the protected senior's line.

*Provider Abstraction*: In Mock mode, downstream services log payloads to an in-memory audit store without making network calls. In Live mode, they route to the Twilio REST API.

---

## 7. Twilio & Live Telephony Boundary

RAKSHA includes a complete telephony integration boundary (`backend/app/services/twilio_service.py`):

- **Dual-Leg Conference Topology**: Inbound calls are routed into a Twilio Conference bridge via TwiML `<Dial><Conference>`. The senior is dialed out on a separate conference leg, enabling unilateral muting, whispering, or termination.
- **Twilio Media Streams**: Audio is forked as an 8kHz `audio/x-mulaw` bi-directional WebSocket stream (`/api/twilio/media-stream`).
- **Deepgram Bridge**: Transcodes telephony audio and streams to Deepgram Nova-2 STT for real-time transcription.
- **Selective Severance**: Disconnects the scammer leg via `client.calls(scammer_call_sid).update(status='completed')`.

### Live Telephony Prerequisites
Running the live telephony path requires external services:
- A Twilio account with Account SID, Auth Token, and a provisioned phone number.
- Public HTTPS/WSS ingress (e.g., via ngrok or Cloudflare Tunnels) for Twilio webhook routing.
- A Deepgram API key (`DEEPGRAM_API_KEY`) for live speech-to-text.
- Outbound calling credits on Twilio.

*The live telephony boundary is covered by unit and integration tests. Full end-to-end PSTN behavior depends on external carrier latency and environment validation.*

---

## 8. Mock / Simulation Mode (Recommended Hackathon Demo)

For hackathons, evaluations, and local demonstrations, RAKSHA provides a **Mock / Simulation Mode**:

- **100% Offline & Reliable**: Runs entirely on `localhost`. Requires zero API keys, no internet connection, and no Twilio balance.
- **Zero Real Telephony Side-Effects**: Does not dial real phones, does not send carrier SMS, and does not disconnect external calls.
- **Identical Pipeline Execution**: Transcripts flow through the exact same `StreamingPipeline`, `SemanticClassifier`, `RiskEngine`, and `ProtectionEngine` used in live mode.
- **Interactive Scenarios**: Includes a pre-configured 5-step Cyber Crime police imposter scam scenario, live browser microphone demonstration mode, manual utterance injection, and instant session resets.

---

## 9. React Cybersecurity Dashboard

The frontend (`frontend/src/`) is a glassmorphic cybersecurity operations dashboard built with React and Vite:

- **Hero Threat Gauge**: Visualizes real-time risk score (`0.0`–`100.0`), active tier, and dominant tactics.
- **Live Dual-Speaker Transcript Feed**: Displays transcribed caller and callee utterances with speech indicators.
- **Manipulation Taxonomy Matrix**: 8 interactive tactic cards displaying activation state, confidence ratings, and timestamps.
- **Tactic Evidence Inspector**: Clickable forensic modal displaying the exact extracted quote and similarity metrics.
- **Chronological Risk Timeline**: Historical graph showing risk score progression turn-by-turn.
- **Active Defense & Response Status**: Real-time operational status of Semantic Analysis, Threat Engine, Caregiver SMS, Audio Whisper, and Line Severance capabilities.
- **Simulation & Demo Suite**: Includes "Simulate Scam Scenario" button (5-turn Indian scam scenario), "Start Browser Mic Demo" (Web Speech API adapter for live speech testing), dual-speaker manual utterance injection, and a clean "New Session" reset button.
- **Visual Waveform**: Live streaming activity visualizer indicating conversational audio presence.

---

## 10. Demo vs. Live Comparison

| Capability | Mock / Simulation Mode | Live Telephony Mode |
| :--- | :--- | :--- |
| **Speech-to-Text** | Local Mock STT / Manual text input | Deepgram Nova-2 streaming WebSocket |
| **Semantic Classifier** | Local Sentence Transformers (`all-MiniLM-L6-v2`) | Local Sentence Transformers (`all-MiniLM-L6-v2`) |
| **Risk Engine** | Production deterministic multi-tactic scoring | Production deterministic multi-tactic scoring |
| **Protection Engine** | Production stateful tier and cooldown policy | Production stateful tier and cooldown policy |
| **Dashboard Telemetry**| Local WebSocket (`/ws/call/{session_id}`) | Local/Remote WebSocket (`/ws/call/{session_id}`) |
| **Caregiver Alert** | Recorded in in-memory notification audit log | Dispatched via Twilio Messaging REST API |
| **User Warning** | Recorded in in-memory warning audit log | Injected TTS audio into callee conference leg |
| **Call Intercept** | Simulated carrier severance log record | Real-time disconnect via Twilio REST API |
| **Credentials Required**| **None** (Fully offline) | Twilio Account SID, Auth Token, Deepgram Key |

---

## 11. Project Structure

```
raksha-scam-detection/
├── ai/                                # AI & Semantic Detection Layer
│   ├── classifier.py                  # Sentence Transformer classifier & cosine matching
│   ├── embeddings.py                  # Local model loading & batch vectorization
│   └── tactics.py                     # Canonical 8-tactic taxonomy & anchor definitions
├── backend/                           # FastAPI Application Core
│   ├── requirements.txt               # Python package dependencies
│   └── app/
│       ├── config.py                  # Pydantic Settings & environment configuration
│       ├── main.py                    # REST API, WebSockets, Twilio webhooks
│       ├── models.py                  # Pydantic domain models & schemas
│       ├── risk_engine.py             # Deterministic multi-tactic risk scoring
│       └── services/
│           ├── connection_manager.py  # WebSocket connection tracking & event broadcast
│           ├── intervention_service.py# Call disconnect abstraction (Mock & Twilio)
│           ├── notification_service.py# Caregiver SMS notification service
│           ├── pipeline.py            # Streaming pipeline orchestrator
│           ├── protection_engine.py   # Stateful protection tier & alert engine
│           ├── session_store.py       # Thread-safe in-memory session repository
│           ├── stt.py                 # Speech-to-text providers (Mock & Deepgram)
│           ├── twilio_service.py      # Twilio signature validation & REST client
│           └── user_warning_service.py# In-call whisper advisory service
├── evaluation/                        # Phase 8B Offline Benchmark Suite
│   ├── metrics.py                     # Metric calculation & aggregation logic
│   ├── models.py                      # Evaluation scenario & result data schemas
│   ├── report.py                      # Structured text & JSON report generators
│   ├── runner.py                      # Isolated benchmark execution harness
│   └── scenarios.py                   # 30 curated multi-turn dialogue scenarios
├── frontend/                          # React Operations Dashboard
│   ├── package.json                   # Node dependencies & Vite scripts
│   ├── vite.config.js                 # Vite bundler configuration & API proxy
│   └── src/
│       ├── App.jsx                    # Root state, WebSocket lifecycle, session reset
│       ├── index.css                  # Custom cyber defense glassmorphic design system
│       └── components/                # Specialized dashboard UI components
├── tests/                             # Test Suite (248 Automated Tests)
├── .env.example                       # Configuration template (zero credentials)
├── .gitignore                         # Standard git ignore definitions
└── README.md                          # Project documentation
```

---

## 12. Local Setup Guide

### Prerequisites
- Python 3.9+
- Node.js 18+ and npm

### 1. Backend Setup

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Start backend server (defaults to Mock mode)
PYTHONPATH=. uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

The backend starts at `http://localhost:8000`. Health check: `http://localhost:8000/health`.

### 2. Frontend Setup

```bash
# In a new terminal window:
cd frontend
npm install
npm run dev
```

Visit `http://localhost:5173` to open the RAKSHA Operations Dashboard.

---

## 13. Step-by-Step Demo Procedure

Follow this procedure for a 3-minute hackathon demonstration:

1. **Start System**: Ensure backend and frontend are running. Open `http://localhost:5173`.
2. **Observe SAFE Baseline**: Verify callee is set to **`Lakshmi R.` (+91 98765 43210)**, Threat Gauge shows `0.0 SAFE`, all tactics are gray, and protection indicates `AVAILABLE`.
3. **Inject Benign Utterance (Optional)**:
   - In the manual injection box, type: `"Namaste Aunty, I'll visit this evening after work."`
   - Click **Inject**. Observe that score remains `0.0 SAFE` with zero tactics triggered.
4. **Trigger Scam Simulation**:
   - Click **Simulate Scam Scenario**.
   - Watch the 5-turn Indian Cyber Crime scam scenario stream automatically into the transcript feed:
     - *Turn 1 (Authority)*: Officer Sharma Cyber Crime Department impersonation detected. Score rises to `SAFE` (~19.3).
     - *Turn 2 (Fear & Intimidation)*: Arrest warrant and bank account freeze. Score escalates to `LOW` (~47.1).
     - *Turn 3 (Urgency & Isolation)*: 15-minute deadline before officers arrive. Score reaches `CRITICAL` (100.0), triggering Priority Intervention Alert modal.
     - *Turn 4 (Secrecy)*: Order not to disconnect or tell family. Risk remains `CRITICAL` (100.0) with cooldown protection.
     - *Turn 5 (Credential Phishing)*: 6-digit OTP verification code demanded. Phishing escalation confirmed.
5. **Live Browser Microphone Demo (Optional)**:
   - Click **🎙 Start Browser Mic Demo** (requires Chrome, Edge, or Safari).
   - Grant microphone permission when prompted.
   - Speak into your microphone: *"This is Officer Sharma from the Cyber Crime Department."*
   - Observe live interim feedback, followed by the finalized transcript routing through the existing WebSocket pipeline.
   - Watch `AUTHORITY_IMPERSONATION` light up dynamically in the Manipulation Taxonomy Matrix.
   - Click **⏹ Stop Browser Mic Demo**.
6. **Inspect Forensic Evidence**:
   - Click any highlighted card in the Manipulation Taxonomy Matrix (e.g., *Authority Impersonation*).
   - View confidence score, timestamp, and exact extracted phrase in the Evidence Inspector modal.
7. **Reset Session**:
   - Click **New Session** in the simulation controls bar.
   - Observe that any active microphone recording stops cleanly, a new unique session ID is generated, the WebSocket cleanly reconnects, and all metrics return to baseline.

> [!NOTE]
> **Operational Mode Architecture**:
> - **Simulation Mode**: Deterministic predefined 5-turn Indian scam scenario streamed through local mock STT.
> - **Browser Mic Demo**: Browser Web Speech API (`SpeechRecognition`) adapter transcribing local user speech into transcript utterances, which enter the exact same RAKSHA detection/risk/protection pipeline over WebSocket. (Does not use Deepgram or carrier PSTN).
> - **Live Telephony Mode**: Production telephony integration boundary connecting Twilio Media Streams (µ-law audio) to Deepgram Nova-2 streaming STT and carrier REST APIs for whisper advisory and scammer leg disconnect.

---

## 14. Testing & Verification

### Running Full Test Suite
The repository includes 248 comprehensive unit, integration, and scenario tests:

```bash
.venv/bin/pytest
```
*Expected baseline: 248 passed, 1 warning (OpenSSL notice).*

### Building Frontend
Validate the production bundle without errors:

```bash
npm --prefix frontend run build
```

### Running Offline Benchmark Suite
Execute the Phase 8B offline scenario evaluation suite:

```bash
.venv/bin/pytest tests/test_evaluation_runner.py -v
```

---

## 15. Offline Evaluation Benchmark (Phase 8B)

RAKSHA was evaluated using a curated benchmark of **30 realistic multi-turn scenarios** comprising **78 dialogue turns** across 7 behavioral categories:

| Category | Scenarios | Focus / Target Behavior |
| :--- | :---: | :--- |
| **`clear_scam`** | 5 | Authority impersonation, arrest threats, gift card demands |
| **`benign`** | 5 | Everyday family calls, customer service, routine banking |
| **`legitimate_urgency`** | 5 | Hospital emergencies, burst pipes, missed urgent flights |
| **`multi_tactic`** | 4 | Dense multi-tactic combinations within single utterances |
| **`novel_wording`** | 5 | Paraphrased scam scripts and novel vocabulary |
| **`progression`** | 3 | Multi-turn trust building slowly escalating to coercion |
| **`downstream_failure`** | 3 | Fault injection (SMS, whisper, and disconnect failures) |

### Key Benchmark Findings
- **Annotated Tactic Match Rate**: **`91.8%`** (45 of 49 annotated ground-truth tactics matched).
- **Benign Escalation in Benchmark**: **`0.0%`** (0 of 5 benign scenarios escalated to `MEDIUM` or higher).
- **Legitimate Urgency Escalation in Benchmark**: **`0.0%`** (0 of 5 legitimate emergency scenarios escalated to `HIGH` or `CRITICAL`).
- **Downstream Failure Isolation**: **`100%`** (3 of 3 injected downstream exceptions were caught and logged without crashing the pipeline).
- **Progression Timing**: First tactic detected at a mean of **`0.24 turns`**; first critical intervention triggered at a mean of **`2.83 turns`**.
- **Novel Wording Generalization**: 4 of 5 novel wording scripts matched target tactics. One technical IT support scenario (*AnyDesk remote access without payment phrasing*) fell below the similarity threshold, identifying a known vocabulary boundary.

*Note: These metrics reflect a curated offline evaluation dataset designed for measurement and regression testing, not a universal guarantee of production accuracy across all possible scam variations.*

---

## 16. Known Limitations

- **Language Scope**: Embeddings and tactic anchors are currently optimized for English-language conversations.
- **Acoustic Nuance**: Transcripts currently evaluate text semantics; acoustic stress, speech rate, and vocal pitch are not factored into the risk score.
- **Novel Technical Jargon**: Novel scam scripts using deep technical or remote-access jargon (without explicit financial or authority terms) can fall below similarity thresholds until explicit extraction occurs.
- **Benchmark Scope**: The 30-scenario offline evaluation is a controlled benchmark; real-world telecommunication environments present broader diversity.
- **Live Carrier Dependencies**: Live PSTN call monitoring relies on network stability, Twilio webhook latency, and Deepgram STT accuracy.

---

## 17. Security & Privacy

- **Offline Semantic Inference**: In local/mock mode, semantic classification runs locally on CPU via Sentence Transformers; zero audio or transcript data is transmitted to third-party model APIs.
- **Environment Isolation**: All credentials are read from environment variables via Pydantic Settings. No secrets, private URLs, or real personal phone numbers are committed to git.
- **Session Isolation**: Each call session maintains isolated in-memory state, preventing cross-call cooldown or risk contamination.

---

## 18. Current Implementation Status

All core components of RAKSHA are implemented and verified:

- [x] Semantic manipulation classifier (`all-MiniLM-L6-v2`) with 8 canonical categories
- [x] Dynamic, deterministic multi-tactic risk engine with synergistic scoring
- [x] Streaming pipeline with sub-500ms event dispatch
- [x] Real-time WebSocket architecture and live connection manager
- [x] Twilio dual-leg conference topology and media stream bridge
- [x] Deepgram Nova-2 streaming speech-to-text integration
- [x] Caregiver SMS notification service with provider abstraction
- [x] Protected-user audio whisper service
- [x] Emergency carrier-level call intervention and severance service
- [x] 3-column cybersecurity operations dashboard with visual streaming activity
- [x] Offline evaluation scenario dataset, runner, and metrics generator
- [x] Demo session reset and WebSocket race condition protection

---

## 19. Future Work

- **Multilingual Semantic Embeddings**: Integrate multilingual sentence models to support multi-language scam detection.
- **Acoustic Emotion Fusion**: Incorporate acoustic features (speech cadence, stress biomarkers, vocal jitter) into the risk engine.
- **Expanded Evaluation Corpus**: Scale the evaluation benchmark to hundreds of real-world scam recordings and adversarial scripts.
- **Telco-Grade Observability**: Add OpenTelemetry tracing and structured Prometheus metrics for carrier deployment.
- **On-Device Mobile Deployment**: Compile semantic embeddings to ONNX / CoreML for client-side smartphone execution.
