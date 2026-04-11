# Claudio

🏆 **1st Place Overall - Claude Builders AI Hackathon, partnered with Anthropic**

[Demo Video](https://www.youtube.com/watch?v=kRd-LZNujkc) &nbsp;|&nbsp; [Devpost](https://devpost.com/software/claudio-yac20h)

---

What if you could just ask where you left something and actually get an answer.

Claudio is a real-time visual memory assistant that runs on a phone camera and builds a searchable memory of a user's environment. It answers natural language questions about their surroundings, past and present, with photographic evidence, in plain English, through voice. It is built for individuals with dementia and designed from the ground up to be simple enough that it never gets in the way.

---

## The Problem

1 in 9 people over 65 have Alzheimer's disease, and misplacing objects is the most commonly reported early symptom among patients and caregivers. Existing tools are too complex, too expensive, or simply do not address the core question people with memory conditions ask dozens of times a day: "Where did I put that?"

Claudio is built around a simple goal: something straightforward enough for an 80-year-old to use, powerful enough to actually help, and affordable enough to run on hardware people already own.

---

## Features

### Natural Language Object Search

Ask "Hey Claudio, where are my keys?" and Claudio responds: "I last saw your keys on the kitchen counter about 12 minutes ago" and surfaces the matching frame. Queries are embedded with CLIP's text encoder, matched against stored image embeddings via cosine similarity, and the top matching frames are sent to Claude Vision, which synthesizes a natural language answer with photographic evidence.

### Always-On Capture

A phone camera continuously monitors the environment, sending frames to the backend every 2 seconds. Frames are embedded locally using CLIP and deduplicated against recent frames before being stored, so the database stays clean without losing meaningful scene changes.

### Voice-First Interface

Claudio runs as a transparent overlay on a live video feed with voice input and voice output via the Web Speech API. Users never need to look down at a keyboard. The UI is high-contrast and non-obtrusive throughout, designed around the research on assistive tech for dementia: intrusive or complex interfaces get abandoned.

---

## Architecture

```
+-------------------------------+
|        Phone Camera           |
|  Frame every 2s via HTTP POST |
+---------------+---------------+
                |
+---------------v---------------+
|       FastAPI Backend         |
|                               |
|  CLIP embed (clip-ViT-B-32)   |
|  Perceptual deduplication     |
|  Supabase + pgvector storage  |
+---------------+---------------+
                |  (query time only)
+---------------v---------------+
|       Claude Vision           |
|  Top-k frame retrieval        |
|  Natural language answer      |
+-------------------------------+
                |
+---------------v---------------+
|     React Frontend            |
|  Live video overlay           |
|  Web Speech API (voice I/O)   |
+-------------------------------+
```

### Capture Pipeline (always-on)

The phone camera sends a frame every 2 seconds via HTTP POST to the FastAPI backend. Each frame is embedded locally using CLIP (`clip-ViT-B-32`) into a 512-dimensional vector, deduplicated against recent frames, and stored in Supabase with pgvector. No external API is called at capture time, keeping it fast and cheap.

### Query Pipeline (on-demand)

When the user asks a question, it is embedded with CLIP's text encoder and matched against stored image embeddings via cosine similarity over a rolling memory window. The top matching frames are sent to Claude Vision, which synthesizes a natural language answer in plain English.

### Frontend

The React frontend renders a live video overlay and uses the Web Speech API for both voice input and output, so the entire interaction is hands-free.

---

## Repo Structure

```
Claudio/
├── frontend/          # React + Vite app with live video overlay and voice I/O
├── backend/           # FastAPI server, CLIP embedding, deduplication, Supabase integration
└── README.md
```

---

## Getting Started

### Prerequisites

- Node.js 18+
- Python 3.10+
- A [Supabase](https://supabase.com/) project with pgvector enabled
- An [Anthropic API key](https://console.anthropic.com/)

### 1. Backend Setup

```bash
cd backend
pip install -r requirements.txt
```

Create a `.env` file:

```
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
ANTHROPIC_API_KEY=your_anthropic_api_key
```

Start the server:

```bash
uvicorn main:app --reload
```

### 2. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` and allow camera and microphone access.

---

## Built With

- [React](https://react.dev/) + [Vite](https://vitejs.dev/) (frontend)
- [FastAPI](https://fastapi.tiangolo.com/) (backend)
- [CLIP (clip-ViT-B-32)](https://github.com/openai/CLIP) (visual embeddings)
- [Claude Vision](https://www.anthropic.com/) (natural language answer synthesis)
- [Supabase](https://supabase.com/) + pgvector (vector storage and semantic search)
- Web Speech API (voice input and output)
