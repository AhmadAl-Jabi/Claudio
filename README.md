# Claudio

AI-powered visual memory assistant. Phone captures your environment, you ask questions, Claude tells you where things are.

---

## Frontend Setup (Ahmad's machine)

**Prerequisites:** Node.js installed, backend already running on Jawdat's machine.

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`. It proxies `/api` and `/ws` to `http://localhost:8000` — make sure the backend is running before opening the app.

---

## ngrok Setup (one-time)

ngrok is needed so the phone can reach the backend over HTTPS (required for camera access).

**Install:**
```bash
npm install -g ngrok
```

**Authenticate (one-time):**
```bash
ngrok config add-authtoken <token from backend/.env NGROK_AUTHTOKEN>
```

**Start tunnel (every session):**
```bash
ngrok http 8000
```

This gives you an `https://` URL. Use it for the phone capture page.

---

## Running Everything (each session)

**Terminal 1 — Backend (Jawdat's machine):**
```bash
cd backend
source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
python main.py
```

**Terminal 2 — Frontend (Ahmad's machine):**
```bash
cd frontend
npm run dev
```

**Terminal 3 — ngrok tunnel:**
```bash
ngrok http 8000
```

---

## Phone Capture

1. Open `https://<ngrok-url>/capture` on your phone
2. Allow camera access
3. Leave Server URL blank (defaults to same origin)
4. Hit **Start Capture**

The phone sends frames to the backend. The laptop frontend at `http://localhost:5173` shows the live feed and chat UI.

---

## Team

| Person | Focus |
|---|---|
| Ahmad | React frontend, voice layer, phone capture app |
| Jawdat | CLIP embeddings, vector search, backend (FastAPI), Supabase |
