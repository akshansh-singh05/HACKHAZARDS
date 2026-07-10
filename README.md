# Personalized Sustainable Shopping Assistant

Local hackathon project that suggests eco-friendly products, tracks purchases, and forecasts carbon/water impact.

Quick start

1. Backend (recommended Python):

```powershell
cd c:\\HACKHAZARDS\\backend
C:/Python314/python.exe -m pip install -r requirements.txt
C:/Python314/python.exe app.py
```

Open http://127.0.0.1:8000 in your browser.

2. Run the ML demo only:

```powershell
cd c:\\HACKHAZARDS\\backend
C:/Python314/python.exe prediction_demo.py
```

Docker (example)

Build and run from the `backend` folder:

```bash
docker build -t sustainable-shopper:latest .
docker run -p 8000:8000 sustainable-shopper:latest
```

Deployment notes
- `backend/Procfile` and `backend/Dockerfile` are provided as examples for Render/Heroku/Vercel.
- The Flask app now respects `PORT` and `HOST`, so it can run in containers and cloud platforms.

## Deploy options

### Docker

From `c:\HACKHAZARDS\backend`:

```bash
docker build -t sustainable-shopper:latest .
docker run -p 8000:8000 -e PORT=8000 -e JWT_SECRET=$(openssl rand -hex 32) sustainable-shopper:latest
```

Then open `http://127.0.0.1:8000`.

### Render / Heroku-style platforms

- Set the start command to the `Procfile` web command: `gunicorn -w 4 -b 0.0.0.0:$PORT app:app`
- Deploy from the `backend` folder.
- Set a `JWT_SECRET` environment variable (a long random string) in the platform's config/secrets.
- No separate frontend app is needed because Flask serves the UI.

### Simple VPS deploy

```bash
cd /path/to/HACKHAZARDS/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PORT=8000 HOST=0.0.0.0 python app.py
```

If you want this exposed publicly, put Nginx or a reverse proxy in front of Gunicorn.

Next improvements
- Persist trained model coefficients and add feature engineering
- Add CI and unit tests for API endpoints

Files of interest
- `backend/app.py` — Flask app + DB seeding
- `backend/prediction.py` — regression model and forecast logic
- `frontend/*` — static UI (served at `/`)

If you want, I can: add auth, persist models, or wire CI. Which should I do next?
# Personalized Sustainable Shopping Assistant

Hackathon project for climate and sustainability systems.

## What it does
- Sign up / log in with a real account (JWT-based auth, passwords hashed with Werkzeug)
- Searches products with sustainability scores
- Filters by category like fashion, food, and home
- Tracks each user's own purchase history in SQLite
- Predicts future carbon and water impact
- Shows a dashboard with charts and monthly savings
- Uses a simple linear regression model trained from monthly purchase history

## Stack
- Frontend: HTML, CSS, JavaScript
- Backend: Flask + SQLite
- Charts: Chart.js

## Run locally

### 1. Backend
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

### 2. Frontend
Open `http://127.0.0.1:8000` in a browser after the backend is running.

### 3. ML demo
```powershell
cd backend
python prediction_demo.py
```

## Auth
Every user-scoped endpoint requires a `Authorization: Bearer <token>` header. Get a token from
`/api/auth/signup` or `/api/auth/login`, then store it (the frontend keeps it in `localStorage`).

Set `JWT_SECRET` in your environment before deploying — the app falls back to an insecure dev
secret otherwise and prints a warning.

A seeded demo account is available: `demo@example.com` / `demo1234` (already has 5 sample
purchases logged, so the dashboard and forecast have data to show immediately).

## API endpoints
- `GET /api/health`
- `POST /api/auth/signup` — `{ name, email, password }` → `{ token, user }`
- `POST /api/auth/login` — `{ email, password }` → `{ token, user }`
- `GET /api/auth/me` — current user (auth required)
- `GET /api/categories`
- `GET /api/products`
- `GET /api/products/{id}`
- `POST /api/purchases` — auth required
- `GET /api/favorites` / `POST /api/favorites` / `DELETE /api/favorites` — auth required
- `GET /api/history` — auth required
- `GET /api/dashboard` — auth required
- `GET /api/predictions` — auth required
