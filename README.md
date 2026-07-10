# Personalized Sustainable Shopping Assistant

A hackathon project that helps users make more sustainable shopping decisions. It lets users sign up, browse products with sustainability scores, track purchases, view their history, and forecast future carbon and water impact.

## Features

- JWT-based authentication with hashed passwords
- Product browsing with sustainability scores
- Category filters for fashion, food, home, and more
- Purchase tracking in SQLite
- Favorites management
- Dashboard with charts and monthly insights
- Carbon and water impact predictions using a simple regression model

## Tech Stack

- Frontend: HTML, CSS, JavaScript
- Backend: Flask
- Database: SQLite
- Charts: Chart.js

## Project Structure

- `backend/app.py` — Flask app, API routes, and database seeding
- `backend/prediction.py` — prediction and forecasting logic
- `frontend/` — static UI served by the backend

## Running Locally

### 1. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Then open:

```text
http://127.0.0.1:8000
```

### 2. ML Demo

```powershell
cd backend
python prediction_demo.py
```

## Authentication

After signing up or logging in, the frontend stores the JWT token in `localStorage`. All user-specific endpoints require this header:

```http
Authorization: Bearer <token>
```

## Demo Account

A seeded demo account is available for testing:

- Email: `demo@example.com`
- Password: `demo1234`

It includes sample purchases so the dashboard and forecasts have data immediately.

## API Endpoints

- `GET /api/health`
- `POST /api/auth/signup` — create a new user
- `POST /api/auth/login` — log in and receive a token
- `GET /api/auth/me` — get the current user
- `GET /api/categories` — list categories
- `GET /api/products` — list products
- `GET /api/products/{id}` — get a single product
- `POST /api/purchases` — add a purchase
- `GET /api/favorites` — list favorites
- `POST /api/favorites` — add a favorite
- `DELETE /api/favorites` — remove a favorite
- `GET /api/history` — view purchase history
- `GET /api/dashboard` — get dashboard data
- `GET /api/predictions` — get impact predictions

## Deployment Notes

- Set `JWT_SECRET` in production.
- The app respects `HOST` and `PORT`, so it works in containers and cloud platforms.
- Example start command for Gunicorn:

```bash
gunicorn -w 4 -b 0.0.0.0:$PORT app:app
```

## Docker

Build and run from the `backend` folder:

```bash
docker build -t sustainable-shopper:latest .
docker run -p 8000:8000 -e PORT=8000 sustainable-shopper:latest
```

## Next Improvements

- Persist trained model coefficients
- Add feature engineering
- Add CI and unit tests for API endpoints
- Improve analytics and forecasting accuracy

