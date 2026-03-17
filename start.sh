#!/bin/bash
# Production startup script for Wizard Store AI backend
# Usage: bash start.sh [--dev]

if [ "$1" = "--dev" ]; then
  echo "Starting in development mode..."
  uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
else
  echo "Starting in production mode..."
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2 --log-level info
fi
