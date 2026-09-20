# Raksha: Real-Time Scam & Manipulation Detection Engine

**Raksha** ("Protection") is an AI-powered real-time scam and psychological manipulation detection system designed to monitor live phone conversations, detect coercive social engineering tactics (urgency, authority impersonation, isolation, financial extraction, panic induction), compute dynamic risk scores, and protect vulnerable individuals.

---

## 10-Phase Roadmap

1. **PHASE 1: Foundation** *(Completed)*
   - FastAPI application with async architecture and CORS
   - Pydantic domain models (`CallSession`, `TranscriptSegment`, `RiskAssessment`, `ManipulationCategory`, `TacticMatch`)
   - Configuration via Pydantic Settings
   - Thread-safe in-memory session store
   - Health check endpoint (`/health`)
   - Real-time WebSocket endpoint (`/ws/call/{session_id}`)
   - AI layer stubs in `ai/` (prepared for Sentence Transformers in Phase 2)
   - React/Vite frontend foundation with cybersecurity glassmorphic UI
   - Unit and integration tests
2. **PHASE 2: Manipulation Detection + Risk Engine** (Sentence Transformers semantic classifier + dynamic co-occurrence scoring)
3. **PHASE 3: Streaming STT** (Speech-to-text pipeline & audio stream converter)
4. **PHASE 4: Real-time WebSocket pipeline** (Sub-500ms event bus)
5. **PHASE 5: Twilio live call integration** (Twilio Media Streams)
6. **PHASE 6: React dashboard** (Full threat visualization, waveforms, tactic breakdown)
7. **PHASE 7: Family alerts + investigator view** (Emergency alerts & forensic reports)
8. **PHASE 8: Novel-script testing + legitimate-call testing** (Adversarial test suite)
9. **PHASE 9: LIVE + DEMO/SIMULATION mode** (Interactive scenario playback & mic simulation)
10. **PHASE 10: Polish + hackathon demo**

---

## Project Structure

```
raksha-scam-detection/
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── __init__.py
│       ├── main.py
│       ├── config.py
│       ├── models.py
│       ├── risk_engine.py
│       └── services/
│           ├── __init__.py
│           └── session_store.py
├── ai/
│   ├── __init__.py
│   ├── embeddings.py
│   ├── classifier.py
│   └── tactics.py
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       └── index.css
├── data/
│   └── .gitkeep
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_health.py
│   ├── test_models.py
│   ├── test_session_store.py
│   └── test_websocket.py
├── .env.example
├── .gitignore
└── README.md
```

---

## Getting Started

### Prerequisites
- Python 3.9+
- Node.js 18+ and npm

### 1. Backend Setup

```bash
# Navigate to backend directory or root
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt

# Run backend test suite
PYTHONPATH=. pytest tests/ -v

# Start backend server
PYTHONPATH=. uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:5173` to view the Raksha foundation dashboard.

### API Endpoints (Phase 1)
- `GET /health`: Health and status check
- `POST /api/sessions`: Create a new call monitoring session
- `GET /api/sessions`: List all call sessions
- `GET /api/sessions/{session_id}`: Retrieve session details and transcript history
- `POST /api/sessions/{session_id}/segments`: Add a transcript segment
- `POST /api/sessions/{session_id}/end`: Mark a session as ended
- `WS /ws/call/{session_id}`: Real-time bi-directional WebSocket stream
