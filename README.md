# 🌱 Personalized Sustainable Shopping Assistant

An intelligent hackathon project that helps users shop more sustainably. Discover eco-friendly products, track your purchases, and see the environmental impact of your buying habits — all in one place.

## ✨ What This Project Does

- 🔐 Secure sign up / log in with JWT authentication
- 🛍️ Browse products with sustainability scores
- 🧭 Filter items by category like fashion, food, home, and more
- 📦 Track purchase history in SQLite
- ⭐ Save favorite products for quick access
- 📊 View a dashboard with charts and monthly insights
- 🌍 Predict future carbon and water impact using a regression model

## 🛠 Tech Stack

- **Frontend:** HTML, CSS, JavaScript
- **Backend:** Flask
- **Database:** SQLite
- **Charts:** Chart.js
- **ML/Prediction:** Simple regression-based forecasting

## 📁 Project Structure

- `backend/app.py` — Flask app, API routes, auth, and database seeding
- `backend/prediction.py` — prediction and forecasting logic
- `backend/prediction_demo.py` — demo script for the ML model
- `frontend/` — user interface served by the backend

## 🚀 Getting Started

### 1) Run the backend

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

### 2) Run the ML demo

```powershell
cd backend
python prediction_demo.py
```

## 🔐 Authentication

After signup or login, the frontend stores the JWT token in `localStorage`. Any user-specific endpoint requires:

```http
Authorization: Bearer <token>
```

## 👤 Demo Account

Use this seeded account to explore the app instantly:

- **Email:** `demo@example.com`
- **Password:** `demo1234`

It already includes sample purchases, so the dashboard and predictions show meaningful data right away.

## 📡 API Endpoints

### Public
- `GET /api/health`
- `POST /api/auth/signup` — create a new user
- `POST /api/auth/login` — log in and receive a token
- `GET /api/categories` — list categories
- `GET /api/products` — list products
- `GET /api/products/{id}` — get a product by ID

### Protected
- `GET /api/auth/me` — get current user profile
- `POST /api/purchases` — add a purchase
- `GET /api/favorites` — list favorites
- `POST /api/favorites` — add a favorite
- `DELETE /api/favorites` — remove a favorite
- `GET /api/history` — view purchase history
- `GET /api/dashboard` — get dashboard analytics
- `GET /api/predictions` — view carbon/water predictions

## 🐳 Docker

Build and run from the `backend` folder:

```bash
docker build -t sustainable-shopper:latest .
docker run -p 8000:8000 -e PORT=8000 sustainable-shopper:latest
```

## ☁️ Deployment Notes

- Set `JWT_SECRET` in production for secure authentication.
- The app respects `HOST` and `PORT`, so it can run in containers and cloud environments.
- Gunicorn start command:

```bash
gunicorn -w 4 -b 0.0.0.0:$PORT app:app
```

## 🔮 Future Improvements

- Persist trained model coefficients
- Add feature engineering for better predictions
- Add CI and unit tests for API endpoints
- Improve analytics and forecasting accuracy
- Enhance UI/UX with more polished visual design

---

💡 **Goal:** make sustainable shopping easier, smarter, and more engaging.
