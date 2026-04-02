#!/bin/bash
set -e
cd frontend
npm run build
mkdir -p ../backend/static
cp -r dist/. ../backend/static/
