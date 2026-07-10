from __future__ import annotations

import csv
import io
import os
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any

import jwt
from flask import Flask, Response, g, jsonify, request, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

try:
    from prediction import build_prediction
except ModuleNotFoundError:  # pragma: no cover - supports package-style imports on Vercel
    from .prediction import build_prediction

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24 * 7  # 1 week

if JWT_SECRET == "dev-secret-change-me" and os.getenv("FLASK_DEBUG") != "1":
    print(
        "WARNING: JWT_SECRET is not set. Using an insecure default. "
        "Set the JWT_SECRET environment variable in production."
    )

BASE_DIR = Path(__file__).resolve().parent.parent
if os.getenv("VERCEL") == "1":
    DB_PATH = Path("/tmp") / "sustainable_shopper.db"
else:
    DB_PATH = BASE_DIR / "backend" / "sustainable_shopper.db"
SEED_PATH = BASE_DIR / "data" / "seed_products.json"
FRONTEND_DIR = BASE_DIR / "frontend"
FRONTEND_INDEX = FRONTEND_DIR / "index.html"

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="/static")


def category_tip(category: str) -> str:
    tips = {
        "food": "Choose seasonal and local produce to reduce transport emissions.",
        "fashion": "Prefer durable fabrics and buy fewer, higher-quality items.",
        "home": "Pick reusable or energy-efficient options for long-term impact reduction.",
    }
    return tips.get(category.lower(), "Pick products with lower CO2 and water footprints.")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def calculate_score(carbon_kg: float, water_liters: float) -> int:
    score = 100 - int((carbon_kg * 8) + (water_liters / 25))
    return max(1, min(100, score))


# --- Review / rating helpers -------------------------------------------------

def get_rating_stats(conn: sqlite3.Connection, product_id: int) -> dict[str, Any]:
    """Average rating (rounded to 1 decimal) and review count for one product."""
    row = conn.execute(
        "SELECT COUNT(*) AS count, AVG(rating) AS avg FROM reviews WHERE product_id = ?",
        (product_id,),
    ).fetchone()
    count = row["count"] or 0
    avg = round(row["avg"], 1) if row["avg"] is not None else 0.0
    return {"average_rating": avg, "review_count": count}


def bulk_rating_stats(conn: sqlite3.Connection, product_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Average rating + review count for many products in a single query."""
    if not product_ids:
        return {}
    placeholders = ",".join("?" for _ in product_ids)
    rows = conn.execute(
        f"""
        SELECT product_id, COUNT(*) AS count, AVG(rating) AS avg
        FROM reviews
        WHERE product_id IN ({placeholders})
        GROUP BY product_id
        """,
        product_ids,
    ).fetchall()
    return {
        row["product_id"]: {
            "average_rating": round(row["avg"], 1) if row["avg"] is not None else 0.0,
            "review_count": row["count"] or 0,
        }
        for row in rows
    }


def serialize_review(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "user_name": row["user_name"],
        "rating": row["rating"],
        "review_text": row["review_text"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# --- Eco-badge / achievement system -----------------------------------------
#
# Badges are derived entirely from data we already compute: the dashboard's
# co2_saved / water_saved totals (kg / L saved against the baseline budget)
# and each purchased product's sustainability_score (averaged, weighted by
# quantity, across a user's purchase history). No new tables are required;
# badge state is calculated on read.

BADGE_DEFINITIONS: list[dict[str, Any]] = [
    # CO2 saved milestones (co2_saved is capped at 120kg by the baseline budget)
    {"id": "co2_10", "category": "co2", "icon": "🌱", "name": "Carbon Rookie",
     "description": "Save 10kg of CO2 through greener purchases", "threshold": 10, "unit": "kg CO2"},
    {"id": "co2_30", "category": "co2", "icon": "🌿", "name": "Carbon Saver",
     "description": "Save 30kg of CO2 through greener purchases", "threshold": 30, "unit": "kg CO2"},
    {"id": "co2_60", "category": "co2", "icon": "🌳", "name": "Carbon Guardian",
     "description": "Save 60kg of CO2 through greener purchases", "threshold": 60, "unit": "kg CO2"},
    {"id": "co2_100", "category": "co2", "icon": "🏆", "name": "Carbon Hero",
     "description": "Save 100kg of CO2 through greener purchases", "threshold": 100, "unit": "kg CO2"},

    # Water saved milestones (water_saved is capped at 4000L by the baseline budget)
    {"id": "water_300", "category": "water", "icon": "💧", "name": "Water Rookie",
     "description": "Save 300L of water through greener purchases", "threshold": 300, "unit": "L water"},
    {"id": "water_1000", "category": "water", "icon": "🌊", "name": "Water Saver",
     "description": "Save 1,000L of water through greener purchases", "threshold": 1000, "unit": "L water"},
    {"id": "water_2000", "category": "water", "icon": "🏞️", "name": "Water Guardian",
     "description": "Save 2,000L of water through greener purchases", "threshold": 2000, "unit": "L water"},
    {"id": "water_3500", "category": "water", "icon": "🐋", "name": "Water Hero",
     "description": "Save 3,500L of water through greener purchases", "threshold": 3500, "unit": "L water"},

    # Average sustainability score across purchase history (1-100 scale)
    {"id": "score_50", "category": "score", "icon": "🍃", "name": "Conscious Shopper",
     "description": "Keep an average sustainability score of 50+", "threshold": 50, "unit": "avg score"},
    {"id": "score_70", "category": "score", "icon": "🌍", "name": "Eco Champion",
     "description": "Keep an average sustainability score of 70+", "threshold": 70, "unit": "avg score"},
    {"id": "score_90", "category": "score", "icon": "✨", "name": "Sustainability Master",
     "description": "Keep an average sustainability score of 90+", "threshold": 90, "unit": "avg score"},
]


def average_sustainability_score(purchase_rows) -> float:
    """Quantity-weighted average sustainability_score across a user's purchases."""
    total_quantity = 0
    weighted_sum = 0.0
    for row in purchase_rows:
        quantity = row["quantity"]
        score = calculate_score(row["carbon_kg"], row["water_liters"])
        weighted_sum += score * quantity
        total_quantity += quantity
    if total_quantity == 0:
        return 0.0
    return weighted_sum / total_quantity


def compute_badges(co2_saved: float, water_saved: float, avg_score: float) -> list[dict[str, Any]]:
    metric_by_category = {"co2": co2_saved, "water": water_saved, "score": avg_score}
    badges = []
    for definition in BADGE_DEFINITIONS:
        current_value = metric_by_category[definition["category"]]
        threshold = definition["threshold"]
        earned = current_value >= threshold
        progress = 100.0 if earned else round(max(0.0, min(100.0, (current_value / threshold) * 100)), 1)
        badges.append(
            {
                **definition,
                "current_value": round(current_value, 2),
                "earned": earned,
                "progress": progress,
            }
        )
    return badges


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT
            )
            """
        )
        # Migration for pre-existing databases created before auth was added.
        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "password_hash" not in existing_columns:
            conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                price REAL NOT NULL,
                carbon_kg REAL NOT NULL,
                water_liters REAL NOT NULL,
                description TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                purchased_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(product_id) REFERENCES products(id)
            )
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO users (id, name, email, password_hash)
            VALUES (1, 'Demo User', 'demo@example.com', ?)
            """,
            (generate_password_hash("demo1234"),),
        )
        # Backfill a password for the demo user if it was created before auth existed.
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = 1 AND (password_hash IS NULL OR password_hash = '')",
            (generate_password_hash("demo1234"),),
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(product_id) REFERENCES products(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cart_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                added_at TEXT NOT NULL,
                UNIQUE(user_id, product_id),
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(product_id) REFERENCES products(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
                review_text TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, product_id),
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(product_id) REFERENCES products(id)
            )
            """
        )
        existing = conn.execute("SELECT COUNT(*) AS count FROM products").fetchone()["count"]
        if existing == 0:
            seed_products = json.loads(SEED_PATH.read_text(encoding="utf-8"))
            seed_rows = [
                (
                    item["name"],
                    item["category"],
                    item["price"],
                    item["carbon_kg"],
                    item["water_liters"],
                    item["description"],
                )
                for item in seed_products
            ]
            conn.executemany(
                """
                INSERT INTO products (name, category, price, carbon_kg, water_liters, description)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                seed_rows,
            )

        purchase_count = conn.execute("SELECT COUNT(*) AS count FROM purchases").fetchone()["count"]
        if purchase_count == 0:
            product_rows = conn.execute("SELECT id, name FROM products").fetchall()
            product_ids = {row["name"]: row["id"] for row in product_rows}
            demo_purchases = [
                (1, product_ids["Organic Cotton T-Shirt"], 1, datetime.utcnow() - timedelta(days=75)),
                (1, product_ids["Seasonal Veggie Basket"], 2, datetime.utcnow() - timedelta(days=52)),
                (1, product_ids["LED Desk Lamp"], 1, datetime.utcnow() - timedelta(days=34)),
                (1, product_ids["Bamboo Toothbrush Set"], 3, datetime.utcnow() - timedelta(days=16)),
                (1, product_ids["Fair-Trade Coffee Bag"], 1, datetime.utcnow() - timedelta(days=7)),
            ]
            conn.executemany(
                """
                INSERT INTO purchases (user_id, product_id, quantity, purchased_at)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (user_id, product_id, quantity, purchased_at.isoformat())
                    for user_id, product_id, quantity, purchased_at in demo_purchases
                ],
            )

        review_count = conn.execute("SELECT COUNT(*) AS count FROM reviews").fetchone()["count"]
        if review_count == 0:
            product_rows = conn.execute("SELECT id, name FROM products").fetchall()
            product_ids = {row["name"]: row["id"] for row in product_rows}
            demo_reviews = [
                (1, product_ids.get("Organic Cotton T-Shirt"), 5,
                 "Soft, holds up after many washes, and the lower footprint makes it an easy pick.",
                 datetime.utcnow() - timedelta(days=70)),
                (1, product_ids.get("Fair-Trade Coffee Bag"), 4,
                 "Great flavor and I like knowing the water impact is lower than my old brand.",
                 datetime.utcnow() - timedelta(days=5)),
            ]
            demo_reviews = [row for row in demo_reviews if row[1] is not None]
            conn.executemany(
                """
                INSERT INTO reviews (user_id, product_id, rating, review_text, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (user_id, product_id, rating, review_text, created_at.isoformat(), created_at.isoformat())
                    for user_id, product_id, rating, review_text, created_at in demo_reviews
                ],
            )
        conn.commit()


def generate_token(user_id: int) -> str:
    payload = {
        "sub": user_id,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def require_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"detail": "Missing or invalid Authorization header"}), 401
        token = auth_header.removeprefix("Bearer ").strip()
        user_id = decode_token(token)
        if user_id is None:
            return jsonify({"detail": "Invalid or expired token"}), 401
        with connect() as conn:
            user = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if user is None:
            return jsonify({"detail": "User not found"}), 401
        g.user_id = user_id
        return view(*args, **kwargs)

    return wrapped


def optional_user_id() -> int | None:
    """Best-effort read of the caller's user id from the Authorization header.

    Unlike require_auth, this never blocks the request — it's used on public
    endpoints (like the product detail page) that want to include extra data
    (e.g. "your review") only when the caller happens to be logged in.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.removeprefix("Bearer ").strip()
    return decode_token(token)


def public_user(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": row["id"], "name": row["name"], "email": row["email"]}


@app.get("/")
def home() -> Any:
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/api/health")
def health() -> Any:
    return jsonify({"status": "ok"})


@app.post("/api/auth/signup")
def signup() -> Any:
    payload = request.get_json(force=True) or {}
    name = (payload.get("name") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    if not name or not email or not password:
        return jsonify({"detail": "name, email, and password are required"}), 400
    if len(password) < 8:
        return jsonify({"detail": "Password must be at least 8 characters"}), 400

    with connect() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing is not None:
            return jsonify({"detail": "An account with that email already exists"}), 409
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash(password)),
        )
        conn.commit()
        user_id = cursor.lastrowid
        user = conn.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,)).fetchone()

    token = generate_token(user_id)
    return jsonify({"token": token, "user": public_user(user)}), 201


@app.post("/api/auth/login")
def login() -> Any:
    payload = request.get_json(force=True) or {}
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    with connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    if user is None or not user["password_hash"] or not check_password_hash(user["password_hash"], password):
        return jsonify({"detail": "Invalid email or password"}), 401

    token = generate_token(user["id"])
    return jsonify({"token": token, "user": public_user(user)})


@app.get("/api/auth/me")
@require_auth
def me() -> Any:
    with connect() as conn:
        user = conn.execute("SELECT id, name, email FROM users WHERE id = ?", (g.user_id,)).fetchone()
    return jsonify(public_user(user))


@app.get("/api/categories")
def get_categories() -> Any:
    with connect() as conn:
        rows = conn.execute("SELECT DISTINCT category FROM products ORDER BY category").fetchall()
    return jsonify([row["category"] for row in rows])


@app.get("/api/products")
def get_products() -> Any:
    query = request.args.get("query", default="")
    category = request.args.get("category", default="all")
    min_price_raw = request.args.get("min_price", default=None)
    max_price_raw = request.args.get("max_price", default=None)

    def parse_price(raw: str | None, field_name: str) -> float | None:
        if raw is None or raw == "":
            return None
        try:
            value = float(raw)
        except ValueError:
            raise ValueError(f"{field_name} must be a number")
        if value < 0:
            raise ValueError(f"{field_name} must be 0 or greater")
        return value

    try:
        min_price = parse_price(min_price_raw, "min_price")
        max_price = parse_price(max_price_raw, "max_price")
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400

    if min_price is not None and max_price is not None and min_price > max_price:
        return jsonify({"detail": "min_price must not be greater than max_price"}), 400

    min_score_raw = request.args.get("min_sustainability_score", default=None)
    max_score_raw = request.args.get("max_sustainability_score", default=None)

    def parse_score(raw: str | None, field_name: str) -> int | None:
        if raw is None or raw == "":
            return None
        try:
            value = int(raw)
        except ValueError:
            raise ValueError(f"{field_name} must be an integer")
        if value < 1 or value > 100:
            raise ValueError(f"{field_name} must be between 1 and 100")
        return value

    try:
        min_score = parse_score(min_score_raw, "min_sustainability_score")
        max_score = parse_score(max_score_raw, "max_sustainability_score")
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400

    if min_score is not None and max_score is not None and min_score > max_score:
        return jsonify({"detail": "min_sustainability_score must not be greater than max_sustainability_score"}), 400

    sql = "SELECT * FROM products WHERE 1=1"
    params: list[Any] = []
    if query:
        sql += " AND LOWER(name) LIKE ?"
        params.append(f"%{query.lower()}%")
    if category and category != "all":
        sql += " AND LOWER(category) = ?"
        params.append(category.lower())
    if min_price is not None:
        sql += " AND price >= ?"
        params.append(min_price)
    if max_price is not None:
        sql += " AND price <= ?"
        params.append(max_price)
    sql += " ORDER BY carbon_kg ASC, water_liters ASC"

    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()

        # sustainability_score is derived from carbon_kg/water_liters rather than
        # stored as its own column, so the range filter is applied in Python
        # against the same calculate_score() used everywhere else in the API.
        if min_score is not None or max_score is not None:
            filtered_rows = []
            for row in rows:
                score = calculate_score(row["carbon_kg"], row["water_liters"])
                if min_score is not None and score < min_score:
                    continue
                if max_score is not None and score > max_score:
                    continue
                filtered_rows.append(row)
            rows = filtered_rows

        rating_map = bulk_rating_stats(conn, [row["id"] for row in rows])

    products = []
    for row in rows:
        stats = rating_map.get(row["id"], {"average_rating": 0.0, "review_count": 0})
        products.append(
            {
                "id": row["id"],
                "name": row["name"],
                "category": row["category"],
                "price": row["price"],
                "carbon_kg": row["carbon_kg"],
                "water_liters": row["water_liters"],
                "sustainability_score": calculate_score(row["carbon_kg"], row["water_liters"]),
                "description": row["description"],
                "average_rating": stats["average_rating"],
                "review_count": stats["review_count"],
            }
        )
    return jsonify(products)


@app.get("/api/products/<int:product_id>")
def get_product(product_id: int) -> Any:
    with connect() as conn:
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if row is None:
            return jsonify({"detail": "Not found"}), 404
        related_rows = conn.execute(
            """
            SELECT id, name, category, carbon_kg, water_liters
            FROM products
            WHERE category = ? AND id != ?
            ORDER BY carbon_kg ASC, water_liters ASC
            LIMIT 3
            """,
            (row["category"], product_id),
        ).fetchall()

        eco_baseline = {
            "fashion": {"carbon_kg": 5.0, "water_liters": 2500.0},
            "food": {"carbon_kg": 3.0, "water_liters": 500.0},
            "home": {"carbon_kg": 4.0, "water_liters": 700.0},
        }
        baseline = eco_baseline.get(row["category"].lower(), {"carbon_kg": 4.0, "water_liters": 800.0})

        co2_saved_vs_baseline = round(max(0.0, baseline["carbon_kg"] - row["carbon_kg"]), 2)
        water_saved_vs_baseline = round(max(0.0, baseline["water_liters"] - row["water_liters"]), 2)

        rating_stats = get_rating_stats(conn, product_id)
        review_rows = conn.execute(
            """
            SELECT r.*, u.name AS user_name
            FROM reviews r
            JOIN users u ON u.id = r.user_id
            WHERE r.product_id = ?
            ORDER BY r.created_at DESC, r.id DESC
            LIMIT 20
            """,
            (product_id,),
        ).fetchall()

        user_review = None
        caller_id = optional_user_id()
        if caller_id is not None:
            own_row = conn.execute(
                """
                SELECT r.*, u.name AS user_name
                FROM reviews r
                JOIN users u ON u.id = r.user_id
                WHERE r.product_id = ? AND r.user_id = ?
                """,
                (product_id, caller_id),
            ).fetchone()
            if own_row is not None:
                user_review = serialize_review(own_row)

        product = {
            "id": row["id"],
            "name": row["name"],
            "category": row["category"],
            "price": row["price"],
            "carbon_kg": row["carbon_kg"],
            "water_liters": row["water_liters"],
            "sustainability_score": calculate_score(row["carbon_kg"], row["water_liters"]),
            "description": row["description"],
            "average_rating": rating_stats["average_rating"],
            "review_count": rating_stats["review_count"],
            "reviews": [serialize_review(r) for r in review_rows],
            "user_review": user_review,
            "details": {
                "tip": category_tip(row["category"]),
                "impact_breakdown": {
                    "co2_saved_vs_category_baseline": co2_saved_vs_baseline,
                    "water_saved_vs_category_baseline": water_saved_vs_baseline,
                },
                "related_products": [
                    {
                        "id": rel["id"],
                        "name": rel["name"],
                        "category": rel["category"],
                        "carbon_kg": rel["carbon_kg"],
                        "water_liters": rel["water_liters"],
                    }
                    for rel in related_rows
                ],
            },
        }
    return jsonify(product)


@app.get("/api/products/<int:product_id>/reviews")
def list_reviews(product_id: int) -> Any:
    with connect() as conn:
        product = conn.execute("SELECT id FROM products WHERE id = ?", (product_id,)).fetchone()
        if product is None:
            return jsonify({"detail": "Product not found"}), 404
        rows = conn.execute(
            """
            SELECT r.*, u.name AS user_name
            FROM reviews r
            JOIN users u ON u.id = r.user_id
            WHERE r.product_id = ?
            ORDER BY r.created_at DESC, r.id DESC
            """,
            (product_id,),
        ).fetchall()
        stats = get_rating_stats(conn, product_id)

    return jsonify(
        {
            "average_rating": stats["average_rating"],
            "review_count": stats["review_count"],
            "reviews": [serialize_review(row) for row in rows],
        }
    )


@app.post("/api/products/<int:product_id>/reviews")
@require_auth
def upsert_review(product_id: int) -> Any:
    """Create or update the caller's review for a product (one review per user per product)."""
    payload = request.get_json(force=True) or {}

    try:
        rating = int(payload.get("rating"))
    except (TypeError, ValueError):
        return jsonify({"detail": "rating must be an integer between 1 and 5"}), 400
    if rating < 1 or rating > 5:
        return jsonify({"detail": "rating must be between 1 and 5"}), 400

    review_text = (payload.get("review_text") or "").strip()
    if len(review_text) > 2000:
        return jsonify({"detail": "review_text must be 2000 characters or fewer"}), 400

    with connect() as conn:
        product = conn.execute("SELECT id FROM products WHERE id = ?", (product_id,)).fetchone()
        if product is None:
            return jsonify({"detail": "Product not found"}), 404

        now = datetime.utcnow().isoformat()
        conn.execute(
            """
            INSERT INTO reviews (user_id, product_id, rating, review_text, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, product_id)
            DO UPDATE SET rating = excluded.rating, review_text = excluded.review_text, updated_at = excluded.updated_at
            """,
            (g.user_id, product_id, rating, review_text, now, now),
        )
        conn.commit()

        own_row = conn.execute(
            """
            SELECT r.*, u.name AS user_name
            FROM reviews r
            JOIN users u ON u.id = r.user_id
            WHERE r.product_id = ? AND r.user_id = ?
            """,
            (product_id, g.user_id),
        ).fetchone()
        stats = get_rating_stats(conn, product_id)

    return (
        jsonify(
            {
                "review": serialize_review(own_row),
                "average_rating": stats["average_rating"],
                "review_count": stats["review_count"],
            }
        ),
        201,
    )


@app.delete("/api/products/<int:product_id>/reviews")
@require_auth
def delete_review(product_id: int) -> Any:
    with connect() as conn:
        conn.execute(
            "DELETE FROM reviews WHERE user_id = ? AND product_id = ?",
            (g.user_id, product_id),
        )
        conn.commit()
        stats = get_rating_stats(conn, product_id)

    return jsonify({"average_rating": stats["average_rating"], "review_count": stats["review_count"]})


@app.post("/api/favorites")
@require_auth
def create_favorite() -> Any:
    payload = request.get_json(force=True)
    user_id = g.user_id
    product_id = int(payload["product_id"])
    with connect() as conn:
        product = conn.execute("SELECT id FROM products WHERE id = ?", (product_id,)).fetchone()
        if product is None:
            return jsonify({"detail": "Product not found"}), 404
        created_at = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT OR IGNORE INTO favorites (user_id, product_id, created_at) VALUES (?, ?, ?)",
            (user_id, product_id, created_at),
        )
        conn.commit()
    return jsonify({"user_id": user_id, "product_id": product_id, "created_at": created_at})


@app.get("/api/favorites")
@require_auth
def list_favorites() -> Any:
    with connect() as conn:
        rows = conn.execute(
            "SELECT pr.* FROM favorites f JOIN products pr ON pr.id = f.product_id WHERE f.user_id = ?",
            (g.user_id,),
        ).fetchall()
        rating_map = bulk_rating_stats(conn, [row["id"] for row in rows])
    products = []
    for row in rows:
        stats = rating_map.get(row["id"], {"average_rating": 0.0, "review_count": 0})
        products.append(
            {
                "id": row["id"],
                "name": row["name"],
                "category": row["category"],
                "price": row["price"],
                "carbon_kg": row["carbon_kg"],
                "water_liters": row["water_liters"],
                "sustainability_score": calculate_score(row["carbon_kg"], row["water_liters"]),
                "description": row["description"],
                "average_rating": stats["average_rating"],
                "review_count": stats["review_count"],
            }
        )
    return jsonify(products)


@app.delete("/api/favorites")
@require_auth
def delete_favorite() -> Any:
    payload = request.get_json(force=True)
    user_id = g.user_id
    product_id = int(payload["product_id"])
    with connect() as conn:
        conn.execute(
            "DELETE FROM favorites WHERE user_id = ? AND product_id = ?",
            (user_id, product_id),
        )
        conn.commit()
    return jsonify({"user_id": user_id, "product_id": product_id})


def _serialize_cart(conn: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT c.id AS cart_id, c.quantity, c.added_at,
               pr.id AS product_id, pr.name, pr.category, pr.price,
               pr.carbon_kg, pr.water_liters, pr.description
        FROM cart_items c
        JOIN products pr ON pr.id = c.product_id
        WHERE c.user_id = ?
        ORDER BY c.added_at DESC, c.id DESC
        """,
        (user_id,),
    ).fetchall()

    items = [
        {
            "cart_id": row["cart_id"],
            "product_id": row["product_id"],
            "name": row["name"],
            "category": row["category"],
            "price": row["price"],
            "quantity": row["quantity"],
            "total_price": round(row["price"] * row["quantity"], 2),
            "carbon_kg": row["carbon_kg"],
            "water_liters": row["water_liters"],
            "description": row["description"],
            "added_at": row["added_at"],
        }
        for row in rows
    ]
    total_items = sum(item["quantity"] for item in items)
    total_price = round(sum(item["total_price"] for item in items), 2)
    return {"items": items, "total_items": total_items, "total_price": total_price}


@app.get("/api/cart")
@require_auth
def get_cart() -> Any:
    with connect() as conn:
        cart = _serialize_cart(conn, g.user_id)
    return jsonify(cart)


@app.post("/api/cart")
@require_auth
def add_to_cart() -> Any:
    """Add to Cart: only ever touches cart_items, never purchases."""
    payload = request.get_json(force=True)
    user_id = g.user_id
    product_id = int(payload["product_id"])
    quantity = int(payload.get("quantity", 1))
    if quantity < 1:
        return jsonify({"detail": "quantity must be at least 1"}), 400

    with connect() as conn:
        product = conn.execute("SELECT id FROM products WHERE id = ?", (product_id,)).fetchone()
        if product is None:
            return jsonify({"detail": "Product not found"}), 404

        added_at = datetime.utcnow().isoformat()
        conn.execute(
            """
            INSERT INTO cart_items (user_id, product_id, quantity, added_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, product_id)
            DO UPDATE SET quantity = quantity + excluded.quantity, added_at = excluded.added_at
            """,
            (user_id, product_id, quantity, added_at),
        )
        conn.commit()
        cart = _serialize_cart(conn, user_id)
    return jsonify(cart), 201


@app.delete("/api/cart")
@require_auth
def remove_from_cart() -> Any:
    """Remove a single line item from the cart without affecting purchase history."""
    payload = request.get_json(force=True)
    user_id = g.user_id
    product_id = int(payload["product_id"])
    with connect() as conn:
        conn.execute(
            "DELETE FROM cart_items WHERE user_id = ? AND product_id = ?",
            (user_id, product_id),
        )
        conn.commit()
        cart = _serialize_cart(conn, user_id)
    return jsonify(cart)


@app.post("/api/cart/checkout")
@require_auth
def checkout_cart() -> Any:
    """Buy Now (from Carts section): moves every cart item into Purchase History, then empties the cart."""
    user_id = g.user_id
    with connect() as conn:
        cart_rows = conn.execute(
            "SELECT product_id, quantity FROM cart_items WHERE user_id = ?",
            (user_id,),
        ).fetchall()

        if not cart_rows:
            return jsonify({"detail": "Cart is empty"}), 400

        purchased_at = datetime.utcnow().isoformat()
        conn.executemany(
            """
            INSERT INTO purchases (user_id, product_id, quantity, purchased_at)
            VALUES (?, ?, ?, ?)
            """,
            [(user_id, row["product_id"], row["quantity"], purchased_at) for row in cart_rows],
        )
        conn.execute("DELETE FROM cart_items WHERE user_id = ?", (user_id,))
        conn.commit()
        cart = _serialize_cart(conn, user_id)

    return jsonify({"purchased_items": len(cart_rows), "purchased_at": purchased_at, "cart": cart})


@app.get("/api/history")
@require_auth
def list_history() -> Any:
    user_id = g.user_id
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                p.id AS purchase_id,
                p.quantity,
                p.purchased_at,
                pr.id AS product_id,
                pr.name,
                pr.category,
                pr.price,
                pr.carbon_kg,
                pr.water_liters,
                pr.description
            FROM purchases p
            JOIN products pr ON pr.id = p.product_id
            WHERE p.user_id = ?
            ORDER BY p.purchased_at DESC, p.id DESC
            """,
            (user_id,),
        ).fetchall()

    history = []
    for row in rows:
        total_price = round(row["price"] * row["quantity"], 2)
        history.append(
            {
                "purchase_id": row["purchase_id"],
                "product_id": row["product_id"],
                "name": row["name"],
                "category": row["category"],
                "price": row["price"],
                "total_price": total_price,
                "quantity": row["quantity"],
                "purchased_at": row["purchased_at"],
                "carbon_kg": row["carbon_kg"],
                "water_liters": row["water_liters"],
                "description": row["description"],
            }
        )
    return jsonify(history)


def _csv_response(rows: list[list[Any]], header: list[str], filename: str) -> Response:
    """Build a downloadable CSV Response from a header row and data rows."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/export/purchase-history.csv")
@require_auth
def export_purchase_history_csv() -> Any:
    """Download the caller's full purchase history as a CSV file."""
    user_id = g.user_id
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                p.id AS purchase_id,
                p.quantity,
                p.purchased_at,
                pr.id AS product_id,
                pr.name,
                pr.category,
                pr.price,
                pr.carbon_kg,
                pr.water_liters
            FROM purchases p
            JOIN products pr ON pr.id = p.product_id
            WHERE p.user_id = ?
            ORDER BY p.purchased_at DESC, p.id DESC
            """,
            (user_id,),
        ).fetchall()

    header = [
        "purchase_id",
        "purchased_at",
        "product_id",
        "product_name",
        "category",
        "quantity",
        "unit_price",
        "total_price",
        "carbon_kg_per_unit",
        "total_carbon_kg",
        "water_liters_per_unit",
        "total_water_liters",
    ]
    data_rows = [
        [
            row["purchase_id"],
            row["purchased_at"],
            row["product_id"],
            row["name"],
            row["category"],
            row["quantity"],
            row["price"],
            round(row["price"] * row["quantity"], 2),
            row["carbon_kg"],
            round(row["carbon_kg"] * row["quantity"], 2),
            row["water_liters"],
            round(row["water_liters"] * row["quantity"], 2),
        ]
        for row in rows
    ]
    return _csv_response(data_rows, header, "purchase_history.csv")


@app.get("/api/export/monthly-impact.csv")
@require_auth
def export_monthly_impact_csv() -> Any:
    """Download the caller's monthly sustainability impact summary as a CSV file."""
    user_id = g.user_id
    with connect() as conn:
        purchases = conn.execute(
            """
            SELECT p.quantity, p.purchased_at, pr.carbon_kg, pr.water_liters
            FROM purchases p
            JOIN products pr ON pr.id = p.product_id
            WHERE p.user_id = ?
            ORDER BY p.purchased_at ASC
            """,
            (user_id,),
        ).fetchall()

    monthly: dict[str, dict[str, float]] = {}
    for row in purchases:
        month = row["purchased_at"][:7]
        impact_co2 = row["carbon_kg"] * row["quantity"]
        impact_water = row["water_liters"] * row["quantity"]
        if month not in monthly:
            monthly[month] = {"co2": 0.0, "water": 0.0}
        monthly[month]["co2"] += impact_co2
        monthly[month]["water"] += impact_water

    header = ["month", "total_carbon_kg", "total_water_liters"]
    data_rows = [
        [month, round(values["co2"], 2), round(values["water"], 2)]
        for month, values in sorted(monthly.items())
    ]
    return _csv_response(data_rows, header, "monthly_sustainability_impact.csv")


def _report_table_style(header_bg: str = "#1b6f3c") -> TableStyle:
    """Shared table styling for the PDF report (header row + zebra striping)."""
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_bg)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f8f3")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]
    )


def _build_sustainability_report_pdf(
    user: sqlite3.Row | None,
    totals: dict[str, Any],
    badges: list[dict[str, Any]],
    history_rows: list[sqlite3.Row],
    monthly: dict[str, dict[str, float]],
) -> bytes:
    """Render the caller's sustainability stats, CO2/water saved, and purchase
    history into a downloadable PDF report and return the raw bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        title="Sustainability Report",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle", parent=styles["Title"], textColor=colors.HexColor("#1b6f3c")
    )
    heading_style = ParagraphStyle(
        "ReportHeading",
        parent=styles["Heading2"],
        textColor=colors.HexColor("#1b6f3c"),
        spaceBefore=18,
        spaceAfter=8,
    )
    body_style = styles["BodyText"]

    elements: list[Any] = [Paragraph("Sustainability Impact Report", title_style)]
    generated_at = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
    elements.append(Paragraph(f"Generated on {generated_at}", body_style))
    if user is not None:
        elements.append(Paragraph(f"Account: {user['name']} ({user['email']})", body_style))
    elements.append(Spacer(1, 0.2 * inch))

    # --- Sustainability summary (CO2 saved, water saved, footprint, score) ---
    elements.append(Paragraph("Sustainability Summary", heading_style))
    summary_rows = [
        ["Metric", "Value"],
        ["CO2 saved vs. baseline", f"{totals['co2_saved']} kg"],
        ["Water saved vs. baseline", f"{totals['water_saved']} L"],
        ["Total carbon footprint", f"{totals['carbon_kg']} kg"],
        ["Total water footprint", f"{totals['water_liters']} L"],
        ["Average sustainability score", f"{totals['average_sustainability_score']} / 100"],
        ["Total purchases", str(totals["purchase_count"])],
    ]
    summary_table = Table(summary_rows, colWidths=[2.8 * inch, 2.8 * inch])
    summary_table.setStyle(_report_table_style())
    elements.append(summary_table)

    # --- Eco badges earned ---
    elements.append(Paragraph("Eco Badges Earned", heading_style))
    earned_badges = [badge for badge in badges if badge.get("earned")]
    if earned_badges:
        badge_rows = [["Badge", "Description"]] + [
            [f"{badge['icon']} {badge['name']}", badge["description"]] for badge in earned_badges
        ]
        badge_table = Table(badge_rows, colWidths=[2.2 * inch, 3.4 * inch])
        badge_table.setStyle(_report_table_style())
        elements.append(badge_table)
    else:
        elements.append(Paragraph("No badges earned yet — keep shopping green!", body_style))

    # --- Monthly CO2 / water impact ---
    if monthly:
        elements.append(Paragraph("Monthly Impact", heading_style))
        monthly_rows = [["Month", "CO2 (kg)", "Water (L)"]] + [
            [month, f"{values['co2']:.2f}", f"{values['water']:.2f}"]
            for month, values in sorted(monthly.items())
        ]
        monthly_table = Table(monthly_rows, colWidths=[1.9 * inch, 1.9 * inch, 1.9 * inch])
        monthly_table.setStyle(_report_table_style())
        elements.append(monthly_table)

    # --- Full purchase history ---
    elements.append(Paragraph("Purchase History", heading_style))
    if history_rows:
        history_table_rows = [["Date", "Product", "Category", "Qty", "CO2 (kg)", "Water (L)"]]
        for row in history_rows:
            history_table_rows.append(
                [
                    row["purchased_at"][:10],
                    row["name"],
                    row["category"],
                    str(row["quantity"]),
                    f"{row['carbon_kg'] * row['quantity']:.2f}",
                    f"{row['water_liters'] * row['quantity']:.2f}",
                ]
            )
        history_table = Table(
            history_table_rows,
            colWidths=[0.9 * inch, 1.9 * inch, 0.9 * inch, 0.5 * inch, 0.9 * inch, 0.9 * inch],
            repeatRows=1,
        )
        history_table.setStyle(_report_table_style())
        elements.append(history_table)
    else:
        elements.append(Paragraph("No purchases recorded yet.", body_style))

    doc.build(elements)
    return buffer.getvalue()


@app.get("/api/export/sustainability-report.pdf")
@require_auth
def export_sustainability_report_pdf() -> Any:
    """Download a PDF report of the caller's sustainability stats, purchase
    history, and total CO2/water saved."""
    user_id = g.user_id
    with connect() as conn:
        user = conn.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,)).fetchone()
        purchases = conn.execute(
            """
            SELECT p.quantity, p.purchased_at, pr.carbon_kg, pr.water_liters
            FROM purchases p
            JOIN products pr ON pr.id = p.product_id
            WHERE p.user_id = ?
            ORDER BY p.purchased_at ASC
            """,
            (user_id,),
        ).fetchall()
        history_rows = conn.execute(
            """
            SELECT p.id AS purchase_id, p.quantity, p.purchased_at, pr.name, pr.category,
                   pr.carbon_kg, pr.water_liters
            FROM purchases p
            JOIN products pr ON pr.id = p.product_id
            WHERE p.user_id = ?
            ORDER BY p.purchased_at DESC, p.id DESC
            """,
            (user_id,),
        ).fetchall()

    total_co2 = 0.0
    total_water = 0.0
    monthly: dict[str, dict[str, float]] = {}
    for row in purchases:
        impact_co2 = row["carbon_kg"] * row["quantity"]
        impact_water = row["water_liters"] * row["quantity"]
        total_co2 += impact_co2
        total_water += impact_water
        month = row["purchased_at"][:7]
        if month not in monthly:
            monthly[month] = {"co2": 0.0, "water": 0.0}
        monthly[month]["co2"] += impact_co2
        monthly[month]["water"] += impact_water

    co2_saved = round(max(0.0, 120.0 - total_co2), 2)
    water_saved = round(max(0.0, 4000.0 - total_water), 2)
    avg_score = average_sustainability_score(purchases)
    badges = compute_badges(co2_saved, water_saved, avg_score)

    pdf_bytes = _build_sustainability_report_pdf(
        user=user,
        totals={
            "carbon_kg": round(total_co2, 2),
            "water_liters": round(total_water, 2),
            "co2_saved": co2_saved,
            "water_saved": water_saved,
            "average_sustainability_score": round(avg_score, 1),
            "purchase_count": len(purchases),
        },
        badges=badges,
        history_rows=history_rows,
        monthly=monthly,
    )

    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="sustainability_report.pdf"'},
    )


@app.post("/api/purchases")
@require_auth
def create_purchase() -> Any:
    payload = request.get_json(force=True)
    user_id = g.user_id
    product_id = int(payload["product_id"])
    quantity = int(payload.get("quantity", 1))
    with connect() as conn:
        product = conn.execute("SELECT id FROM products WHERE id = ?", (product_id,)).fetchone()
        if product is None:
            return jsonify({"detail": "Product not found"}), 404
        purchased_at = datetime.utcnow().isoformat()
        cursor = conn.execute(
            """
            INSERT INTO purchases (user_id, product_id, quantity, purchased_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, product_id, quantity, purchased_at),
        )
        conn.commit()
    response = {
        "id": cursor.lastrowid,
        "user_id": user_id,
        "product_id": product_id,
        "quantity": quantity,
        "purchased_at": purchased_at,
    }
    return jsonify(response)


@app.get("/api/dashboard")
@require_auth
def get_dashboard() -> Any:
    user_id = g.user_id
    with connect() as conn:
        purchases = conn.execute(
            """
            SELECT p.quantity, p.purchased_at, pr.name, pr.category, pr.carbon_kg, pr.water_liters
            FROM purchases p
            JOIN products pr ON pr.id = p.product_id
            WHERE p.user_id = ?
            ORDER BY p.purchased_at ASC
            """,
            (user_id,),
        ).fetchall()
        favorites = conn.execute(
            """
            SELECT pr.id, pr.name, pr.category, pr.price, pr.carbon_kg, pr.water_liters, pr.description
            FROM favorites f
            JOIN products pr ON pr.id = f.product_id
            WHERE f.user_id = ?
            ORDER BY f.created_at DESC, f.id DESC
            """,
            (user_id,),
        ).fetchall()
        history_with_price = conn.execute(
            """
            SELECT p.id AS purchase_id, p.quantity, p.purchased_at, pr.id AS product_id, pr.name, pr.category, pr.price,
                   pr.carbon_kg, pr.water_liters, pr.description
            FROM purchases p
            JOIN products pr ON pr.id = p.product_id
            WHERE p.user_id = ?
            ORDER BY p.purchased_at DESC, p.id DESC
            """,
            (user_id,),
        ).fetchall()
        favorites_rating_map = bulk_rating_stats(conn, [row["id"] for row in favorites])

    monthly: dict[str, dict[str, float]] = {}
    total_co2 = 0.0
    total_water = 0.0
    for row in purchases:
        month = row["purchased_at"][:7]
        impact_co2 = row["carbon_kg"] * row["quantity"]
        impact_water = row["water_liters"] * row["quantity"]
        total_co2 += impact_co2
        total_water += impact_water
        if month not in monthly:
            monthly[month] = {"co2": 0.0, "water": 0.0}
        monthly[month]["co2"] += impact_co2
        monthly[month]["water"] += impact_water

    history_items = [
        {
            "purchase_id": row["purchase_id"],
            "product_id": row["product_id"],
            "name": row["name"],
            "category": row["category"],
            "price": row["price"],
            "total_price": round(row["price"] * row["quantity"], 2),
            "quantity": row["quantity"],
            "purchased_at": row["purchased_at"],
            "carbon_kg": row["carbon_kg"],
            "water_liters": row["water_liters"],
            "description": row["description"],
        }
        for row in history_with_price
    ]

    savings_co2 = round(max(0.0, 120.0 - total_co2), 2)
    savings_water = round(max(0.0, 4000.0 - total_water), 2)
    avg_score = average_sustainability_score(purchases)
    badges = compute_badges(savings_co2, savings_water, avg_score)

    return jsonify({
        "totals": {
            "carbon_kg": round(total_co2, 2),
            "water_liters": round(total_water, 2),
            "co2_saved": savings_co2,
            "water_saved": savings_water,
            "average_sustainability_score": round(avg_score, 1),
        },
        "badges": badges,
        "badge_summary": {
            "earned": sum(1 for badge in badges if badge["earned"]),
            "total": len(badges),
        },
        "monthly": [
            {"month": month, "co2": round(values["co2"], 2), "water": round(values["water"], 2)}
            for month, values in sorted(monthly.items())
        ],
        "purchase_count": len(purchases),
        "favorites": [
            {
                "id": row["id"],
                "name": row["name"],
                "category": row["category"],
                "price": row["price"],
                "carbon_kg": row["carbon_kg"],
                "water_liters": row["water_liters"],
                "sustainability_score": calculate_score(row["carbon_kg"], row["water_liters"]),
                "description": row["description"],
                "average_rating": favorites_rating_map.get(row["id"], {"average_rating": 0.0})["average_rating"],
                "review_count": favorites_rating_map.get(row["id"], {"review_count": 0})["review_count"],
            }
            for row in favorites
        ],
        "history": history_items,
    })


@app.get("/api/badges")
@require_auth
def get_badges() -> Any:
    """Standalone eco-badge endpoint, reusing the same logic as /api/dashboard."""
    user_id = g.user_id
    with connect() as conn:
        purchases = conn.execute(
            """
            SELECT p.quantity, pr.carbon_kg, pr.water_liters
            FROM purchases p
            JOIN products pr ON pr.id = p.product_id
            WHERE p.user_id = ?
            """,
            (user_id,),
        ).fetchall()

    total_co2 = sum(row["carbon_kg"] * row["quantity"] for row in purchases)
    total_water = sum(row["water_liters"] * row["quantity"] for row in purchases)
    savings_co2 = round(max(0.0, 120.0 - total_co2), 2)
    savings_water = round(max(0.0, 4000.0 - total_water), 2)
    avg_score = average_sustainability_score(purchases)
    badges = compute_badges(savings_co2, savings_water, avg_score)

    return jsonify({
        "totals": {
            "co2_saved": savings_co2,
            "water_saved": savings_water,
            "average_sustainability_score": round(avg_score, 1),
        },
        "badges": badges,
        "badge_summary": {
            "earned": sum(1 for badge in badges if badge["earned"]),
            "total": len(badges),
        },
    })


@app.get("/api/predictions")
@require_auth
def get_predictions() -> Any:
    user_id = g.user_id
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT pr.carbon_kg, pr.water_liters, p.quantity, p.purchased_at
            FROM purchases p
            JOIN products pr ON pr.id = p.product_id
            WHERE p.user_id = ? AND p.purchased_at >= datetime('now', '-365 days')
            ORDER BY p.purchased_at ASC
            """,
            (user_id,),
        ).fetchall()

        # If no purchases in the last year, fall back to all history
        if not rows:
            rows = conn.execute(
                """
                SELECT pr.carbon_kg, pr.water_liters, p.quantity, p.purchased_at
                FROM purchases p
                JOIN products pr ON pr.id = p.product_id
                WHERE p.user_id = ?
                ORDER BY p.purchased_at ASC
                """,
                (user_id,),
            ).fetchall()

    return jsonify(build_prediction(rows))


init_db()


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, host=host, port=port)
