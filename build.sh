#!/bin/bash
set -e

echo "==> Installing Python dependencies..."
pip install -r backend/requirements.txt --quiet

echo "==> Installing frontend dependencies..."
cd frontend
npm ci

echo "==> Building frontend..."
npm run build

echo "==> Copying dist to backend/static..."
cd ..
mkdir -p backend/static
cp -r frontend/dist/. backend/static/

echo "==> Build complete."
