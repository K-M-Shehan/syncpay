#!/bin/bash
# run_cluster.sh - Start SyncPay cluster

echo "🚀 Starting SyncPay Distributed Payment System"

# Kill any existing processes
pkill -f "python.*main.py" 2>/dev/null || true
sleep 2

# Start nodes in background
echo "Starting Node 1 (Port 5000)..."
cd src && python main.py node1 > ../logs/node1.log 2>&1 &
NODE1_PID=$!

sleep 2

echo "Starting Node 2 (Port 5001)..."
python main.py node2 > ../logs/node2.log 2>&1 &
NODE2_PID=$!

sleep 2

echo "Starting Node 3 (Port 5002)..."  
python main.py node3 > ../logs/node3.log 2>&1 &
NODE3_PID=$!

# Create logs directory if it doesn't exist
mkdir -p ../logs

echo "SyncPay cluster started!"
echo "   Node 1: http://localhost:5000 (PID: $NODE1_PID)"
echo "   Node 2: http://localhost:5001 (PID: $NODE2_PID)" 
echo "   Node 3: http://localhost:5002 (PID: $NODE3_PID)"
echo ""
echo "Test the system:"
echo "   curl -X POST http://localhost:5000/payment -H 'Content-Type: application/json' -d '{\"amount\": 100.50, \"sender\": \"alice\", \"receiver\": \"bob\"}'"
echo ""
echo "Check status:"
echo "   curl http://localhost:5000/status"
echo ""
echo "View logs:"
echo "   tail -f logs/node1.log"
echo ""
echo "To stop cluster: ./stop_cluster.sh"

# Save PIDs for stopping later
echo "$NODE1_PID $NODE2_PID $NODE3_PID" > .pids
