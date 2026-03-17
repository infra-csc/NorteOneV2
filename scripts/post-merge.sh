#!/bin/bash
set -e

cd /home/runner/workspace

if [ -f "frontend/package.json" ]; then
  cd frontend && npm install --prefer-offline --no-audit --no-fund 2>/dev/null && cd ..
fi

if [ -f "backend/requirements.txt" ]; then
  cd backend && pip install -q -r requirements.txt 2>/dev/null && cd ..
fi

echo "Post-merge setup complete"
