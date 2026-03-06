#!/bin/bash
set -e
cd /home/runner/workspace/frontend
npm run build
mkdir -p /home/runner/workspace/backend/static
cp -r /home/runner/workspace/frontend/dist/. /home/runner/workspace/backend/static/
