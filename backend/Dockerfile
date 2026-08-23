# syntax=docker/dockerfile:1

FROM python:3.13-slim

# Prevent .pyc files and enable unbuffered stdout/stderr logging.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# ASGI server: this project uses Django Channels for websockets
# (notifications/routing.py), served via Daphne (already in requirements.txt)
# through bookings/asgi.py. Migrations and collectstatic are intentionally
# NOT run here — run them as separate, explicit steps.
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "bookings.asgi:application"]
