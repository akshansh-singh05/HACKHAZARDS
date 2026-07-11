FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY . .

CMD ["sh", "-c", "gunicorn -w 4 -b 0.0.0.0:${PORT:-8000} backend.app:app"]