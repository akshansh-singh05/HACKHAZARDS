import os

try:
	from backend.app import app
except ModuleNotFoundError:
	from .app import app
except ImportError:  # pragma: no cover - supports running this file directly
    from app import app


if __name__ == "__main__":
	host = os.getenv("HOST", "0.0.0.0")
	port = int(os.getenv("PORT", "8000"))
	app.run(debug=True, host=host, port=port)
