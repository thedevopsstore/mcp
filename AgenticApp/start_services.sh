#!/bin/bash
# Startup script to run both backend server and Streamlit frontend

set -e

# Create sessions directory if it doesn't exist
mkdir -p /app/sessions

# Start the backend server in the background
echo "🚀 Starting DevOps Supervisor Agent backend server..."
echo "   Backend will run on: ${A2A_HOST:-0.0.0.0}:${A2A_PORT:-9000}"
uv run python supervisor_with_aws_agent.py > /app/logs/backend.log 2>&1 &
BACKEND_PID=$!

# Wait a moment for backend to start
echo "⏳ Waiting for backend to initialize..."
sleep 5

# Check if backend is running
if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo "❌ Backend server failed to start"
    echo "   Check logs: /app/logs/backend.log"
    cat /app/logs/backend.log || true
    exit 1
fi

# Check if backend is listening on port
if ! nc -z localhost ${A2A_PORT:-9000} 2>/dev/null; then
    echo "⚠️  Backend may not be ready yet, continuing anyway..."
else
    echo "✅ Backend server is listening on port ${A2A_PORT:-9000}"
fi

echo "✅ Backend server started (PID: $BACKEND_PID)"

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Shutting down services..."
    if kill -0 $BACKEND_PID 2>/dev/null; then
        echo "   Stopping backend server (PID: $BACKEND_PID)..."
        kill $BACKEND_PID 2>/dev/null || true
        wait $BACKEND_PID 2>/dev/null || true
    fi
    echo "✅ Shutdown complete"
    exit 0
}

# Trap signals to cleanup
trap cleanup SIGTERM SIGINT

# Start Streamlit frontend in foreground
echo ""
echo "🚀 Starting Streamlit frontend..."
echo "   Frontend will run on: ${STREAMLIT_SERVER_ADDRESS:-0.0.0.0}:${STREAMLIT_SERVER_PORT:-8501}"
echo "   Backend URL: http://localhost:${A2A_PORT:-9000}"
echo ""

uv run streamlit run streamlit_agent_ui.py \
    --server.port=${STREAMLIT_SERVER_PORT:-8501} \
    --server.address=${STREAMLIT_SERVER_ADDRESS:-0.0.0.0} \
    --server.headless=true \
    --browser.gatherUsageStats=false

# If Streamlit exits, cleanup backend
cleanup

