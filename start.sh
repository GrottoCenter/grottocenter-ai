#!/bin/bash

# Start backend in background
echo "Starting backend server..."
python run_backend.py &
BACKEND_PID=$!

# Wait a moment for backend to start
sleep 5

# Start frontend
echo "Starting frontend server..."
python run_frontend.py &
FRONTEND_PID=$!

# Function to handle shutdown
shutdown() {
    echo "Shutting down services..."
    kill $BACKEND_PID $FRONTEND_PID
    wait $BACKEND_PID $FRONTEND_PID
    echo "All services stopped."
    exit 0
}

# Trap signals to ensure clean shutdown
trap shutdown SIGTERM SIGINT

# Wait for both processes
wait $BACKEND_PID $FRONTEND_PID