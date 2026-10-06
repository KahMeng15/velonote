#!/bin/bash

# velonote Local Development Script
# Run locally bare-metal or pass --docker to launch full containerized stack.

if [ "$1" = "--docker" ] || [ "$1" = "-d" ]; then
    shift
    echo "Starting velonote dev containers with file watchers..."
    exec docker compose -f docker-compose.dev.yml up "$@"
fi

# 1. Ensure logs directory exists
mkdir -p logs

# 2. Start the Background Worker in the background
echo "Starting Background Worker..."
# Kill any existing zombie workers first
pkill -f "python3 -m app.worker_main" || true
python3 -m app.worker_main > logs/worker_stdout.log 2>&1 &
WORKER_PID=$!

# 3. Start the React Frontend Dev Server in the background
echo "Starting React Frontend on http://localhost:5173..."
(cd frontend && npm run dev > ../logs/frontend_stdout.log 2>&1) &
FRONTEND_PID=$!


# Cleanup on exit (Must be defined before blocking commands)
trap "kill $WORKER_PID $FRONTEND_PID; exit" SIGINT SIGTERM

# 4. Start the API Server (blocking)
echo "Starting API Server on http://localhost:8000..."
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
