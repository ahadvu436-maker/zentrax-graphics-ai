# Zentrax AI

Zentrax AI is a full-stack platform for generating logos, banners, and other
graphic design assets from natural-language prompts. Users describe what they
want, choose a design type, and Zentrax's AI generation pipeline produces a
downloadable image in seconds.

The project is split into two independently deployable layers:

- **Frontend** — a Next.js (App Router) application that provides the prompt
  form, live preview, and result gallery.
- **Backend** — a FastAPI service that validates requests, drives image
  generation (via Stable Diffusion or an external generation API), uploads
  results to cloud storage, and returns a public image URL.

---

## Table of Contents

- [Overview](#overview)
- [Tech Stack](#tech-stack)
- [Folder Structure](#folder-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Backend Setup](#backend-setup)
  - [Frontend Setup](#frontend-setup)
  - [Running with Docker](#running-with-docker)
- [Environment Variables](#environment-variables)
- [API Usage](#api-usage)
- [Development Scripts](#development-scripts)
- [Contributing](#contributing)

---

## Overview

**Core flow:**

1. A user enters a text prompt and selects a design type (logo or banner) in
   the frontend.
2. The frontend sends a `POST` request to the FastAPI backend with the prompt
   and design parameters.
3. The backend's AI engine (`app/services/ai_engine.py`) builds a
   style-augmented prompt and calls the configured generation service
   (Stable Diffusion API or a locally-hosted `diffusers` pipeline).
4. The resulting image is uploaded to cloud storage (`app/services/storage.py`
   — AWS S3 or Cloudinary) and a public URL is generated.
5. The backend returns a structured JSON response with the image URL, which
   the frontend renders in the preview area with graceful loading and
   fallback states.

---

## Tech Stack

### Backend
- **FastAPI** — async Python web framework
- **Pydantic v2 / pydantic-settings** — request validation & environment
  config management
- **Uvicorn** — ASGI server
- **Stable Diffusion (`diffusers`, `torch`)** or an external generation API —
  image generation
- **boto3 / cloudinary** — cloud storage upload
- **python-jose / passlib** — JWT auth & password hashing

### Frontend
- **Next.js 14 (App Router)** — React framework
- **React 18** — UI library
- **TypeScript** — static typing
- **Tailwind CSS** — utility-first styling
- **Axios** — HTTP client for backend communication

### Infrastructure
- **Docker** — multi-stage builds for both services
- **AWS S3 / Cloudinary** — generated asset storage
- **PostgreSQL** (optional) — persistence layer for users / generation history

---

## Folder Structure

```
zentrax-ai/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── endpoints.py        # Route definitions
│   │   ├── core/
│   │   │   ├── config.py           # Settings via pydantic-settings
│   │   │   └── security.py         # JWT auth & password hashing
│   │   ├── models/
│   │   │   └── schemas.py          # Pydantic request/response schemas
│   │   ├── services/
│   │   │   ├── ai_engine.py        # Generation logic (SD / external API)
│   │   │   └── storage.py          # S3 / Cloudinary upload service
│   │   └── main.py                 # FastAPI app entrypoint
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── Dockerfile
│   └── .dockerignore
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   └── page.tsx            # Main generator page
│   │   ├── components/
│   │   │   ├── GeneratorForm.tsx   # Prompt + design type form
│   │   │   └── ResultDisplay.tsx   # Image preview with fallback handling
│   │   ├── services/
│   │   │   └── api.ts              # Axios client for backend calls
│   │   └── styles/
│   │       └── globals.css         # Tailwind base styles & design tokens
│   ├── public/
│   │   ├── images/
│   │   │   ├── logo/
│   │   │   └── placeholders/
│   │   └── icons/
│   ├── package.json
│   ├── tailwind.config.js
│   └── next.config.js
│
├── docker-compose.yml
└── README.md
```

---

## Getting Started

### Prerequisites

- **Node.js** ≥ 18.17
- **Python** ≥ 3.11
- **Docker** & **Docker Compose** (optional, for containerized setup)
- An account/API key for your chosen generation provider (e.g. Stability AI)
  and storage provider (AWS S3 or Cloudinary)

### Backend Setup

```bash
cd backend

# Create and activate a virtual environment
python3.11 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env             # then fill in the values (see below)

# Run the development server
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`, with interactive docs
at `http://localhost:8000/docs`.

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Configure environment variables
cp .env.local.example .env.local   # then set NEXT_PUBLIC_API_BASE_URL

# Run the development server
npm run dev
```

The app will be available at `http://localhost:3000`.

### Running with Docker

```bash
# From the project root
docker compose up --build
```

This builds and starts both the backend and frontend containers. The backend
Dockerfile uses a multi-stage build and (by default) a CUDA base image for
GPU-accelerated inference — see the comments in `backend/Dockerfile` for how
to switch to a CPU-only or external-API-only setup.

---

## Environment Variables

**`backend/.env`**

| Variable | Description |
|---|---|
| `SECRET_KEY` | Secret used to sign JWTs (min 32 chars) |
| `DATABASE_URL` | Database connection string |
| `AI_GENERATION_API_KEY` | API key for the external generation provider |
| `AI_GENERATION_BASE_URL` | Base URL for the generation provider |
| `STORAGE_BACKEND` | `s3` or `cloudinary` |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | AWS credentials (if using S3) |
| `AWS_REGION` / `AWS_S3_BUCKET` | S3 bucket configuration |
| `CLOUDINARY_URL` | Cloudinary connection string (if using Cloudinary) |
| `BACKEND_CORS_ORIGINS` | Comma-separated list of allowed frontend origins |

**`frontend/.env.local`**

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Base URL of the FastAPI backend (e.g. `http://localhost:8000`) |

---

## API Usage

### Generate a logo

```bash
curl -X POST http://localhost:8000/api/v1/design/logo/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A modern geometric fox mascot logo",
    "brand_name": "Brewhaus",
    "tagline": "Coffee, crafted daily",
    "style": "minimalist",
    "resolution": "1024x1024",
    "transparent_background": true
  }'
```

**Response**

```json
{
  "request_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "completed",
  "design_type": "logo",
  "prompt": "A modern geometric fox mascot logo",
  "style": "minimalist",
  "assets": [
    {
      "asset_id": "9c858901-8a57-4791-81fe-4c455b099bc9",
      "file_url": "https://cdn.zentrax.ai/generated/logo/abc123.png",
      "thumbnail_url": "https://cdn.zentrax.ai/generated/logo/abc123_thumb.png",
      "resolution": "1024x1024"
    }
  ],
  "created_at": "2026-09-10T12:00:00Z",
  "completed_at": "2026-09-10T12:00:03Z"
}
```

### Generate a banner / image

```bash
curl -X POST http://localhost:8000/api/v1/design/image/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A wide banner of a sunset over a mountain range, warm tones",
    "design_type": "banner",
    "style": "realistic",
    "resolution": "1500x500",
    "num_variations": 2
  }'
```

### Check generation status (if using async/polling)

```bash
curl http://localhost:8000/api/v1/design/status/3fa85f64-5717-4562-b3fc-2c963f66afa6
```

Full interactive request/response schemas are available via the
auto-generated Swagger UI at `/docs` once the backend is running.

---

## Development Scripts

**Backend**

```bash
pytest                 # run tests
black app/              # format code
ruff check app/          # lint
```

**Frontend**

```bash
npm run lint         # lint
npm run type-check   # TypeScript type checking
npm run build         # production build
```

---

## Contributing

1. Fork the repository and create a feature branch.
2. Follow the existing code style (`black`/`ruff` for Python, `eslint` for
   TypeScript).
3. Add or update tests where relevant.
4. Open a pull request with a clear description of the change.