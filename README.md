# syncpay

>a distributed payments system

## Scenario
You are required to design and implement a prototype for a simplified Distributed Payment Processing System used by an e-commerce platform. The system should support multiple clients performing payment transactions concurrently, ensuring that all payments are recorded correctly and consistently even in the presence of node failures or network delays. The historical payment details should be accessible from any server to any client. 

 
## Tasks
Divide the tasks among the 4 team members, ensuring collaboration and integration of all components. Each member will focus on one core aspect of the system, but the team must work together to ensure the system functions as a whole.

1. Fault Tolerance (Member 1):
Objective: Ensure the system continues functioning even in case of failures.
Tasks:
- Implement redundancy mechanisms across multiple servers.
- Design a failure detection system to identify when a payment server node becomes unavailable.
- Develop an automatic failover mechanism to redirect payments in case of server failures.
- Propose a recovery mechanism for nodes that rejoin the system.
- Evaluate the impact of redundancy on system performance and storage overhead.
  
2. Data Replication and Consistency (Member 2):
Objective: Ensure payment details (ledger) are replicated across multiple nodes while maintaining consistency and availability.
Tasks:
- Design a replication strategy (e.g., quorum-based, primary-backup, or sharding).
- Choose a consistency model (e.g., strong consistency, eventual consistency) and justify the trade-offs.
- Implement a deduplication mechanism to handle duplicates caused by retries or failovers.
- Optimize payment performance while ensuring consistency across servers.
- Analyze how replication impacts latency and storage efficiency.
  
3. Time Synchronization (Member 3):
Objective: Ensure payment details have accurate timestamps for event correlation and debugging across distributed servers.
Tasks:
- Implement a time synchronization protocol (e.g., NTP, PTP) across all logging nodes.
- Analyze the impact of clock skew on log ordering and consistency.
- Develop a mechanism to reorder logs that arrive out of sequence due to network delays.
- Implement log timestamp correction techniques to ensure event accuracy.
- Evaluate the trade-offs between synchronization accuracy and system overhead.
  
4. Consensus and Agreement Algorithms (Member 4):
Objective: Ensure distributed payment servers agree on log storage, indexing, and retrieval policies.
Tasks:
- Research and implement a consensus algorithm (e.g., Raft, Paxos) for distributed payment consistency.
- Design a leader election mechanism to manage payment coordination.
- Evaluate the performance of the consensus algorithm under high payment processing rates.
- Propose optimizations to reduce consensus overhead while ensuring consistency.
- Test the system under different failure scenarios (network partitions, node crashes).

## Overall Tech Stack
  
- Language: Python 3.x
- Communication: Flask or FastAPI (HTTP API between nodes)
- Networking (RPC): grpcio (for more efficient node-to-node communication)
- Data Storage: SQLite/PostgreSQL (with SQLAlchemy ORM)
- Threading/Concurrency: threading or asyncio
- Testing & Simulation: pytest + unittest.mock
- Containerization (optional): Docker for simulating multiple servers locally

## Team Member Task Breakdown

Member 1 – Fault Tolerance
Libraries & Tools:
threading for failure detection pings
requests or grpcio for health checks
apscheduler for periodic tasks (e.g., failover checks)
Implementation Plan:
Failure Detection:
Each node runs a small health-check endpoint /health.
Periodically ping all nodes to detect downtime.
Automatic Failover:
Maintain a list of active nodes; if a primary is down, reassign to a backup node.
Recovery:
When a node comes back online, it requests the latest ledger updates from a healthy node.
Performance Evaluation:
Measure response time impact when failover occurs.
Example Module: fault_tolerance.py

Member 2 – Data Replication & Consistency
Libraries & Tools:
Flask or FastAPI for transaction endpoints
SQLAlchemy ORM for database access
json for payment ledger serialization
uuid for unique transaction IDs (helps deduplication)
Implementation Plan:
Replication Strategy:
Use primary-backup: one primary node sends each new transaction to all replicas.
Consistency Model:
Strong consistency — transaction only confirmed after majority ack.
Deduplication:
Maintain transaction_id in DB to avoid reapplying duplicates after failover.
Performance Optimization:
Batch replication updates to reduce network calls.
Example Module: replication.py

Member 3 – Time Synchronization
Libraries & Tools:
ntplib for NTP sync
Python’s datetime for timestamps
heapq for reordering logs based on time
Implementation Plan:
Clock Sync:
Periodically sync system clock with NTP server.
Impact of Skew:
Simulate skew and measure ordering errors.
Reorder Logs:
Use priority queue to reorder events if they arrive out of sequence.
Timestamp Correction:
Apply offset corrections when skew detected.
Example Module: time_sync.py

Member 4 – Consensus & Agreement
Libraries & Tools:
raftos (Raft consensus in Python)
threading or asyncio for leader election tasks
Implementation Plan:
Consensus Algorithm:
Implement Raft to agree on payment log ordering.
Leader Election:
Use Raft’s built-in leader selection mechanism.
Performance Evaluation:
Test under 1000+ concurrent payment requests.
Optimization:
Reduce heartbeat interval for faster failover detection.
Example Module: consensus.py

## Integration Plan
- Common Ledger API (ledger_api.py):
- Endpoints for /pay, /get_ledger, /health.
- Startup Script (main.py):
- Starts Flask/FastAPI server
- Connects modules from all 4 members
- Configuration File (config.json):
- Holds list of node IPs, ports, primary/backup roles.
- Testing Script (test_system.py):
- Simulates multiple clients sending payments.
- Docker Compose Setup (optional):
- Simulates multiple distributed nodes on one machine.

## Quick Start
```bash
# Create virtual environment (one time only)
python3 -m venv syncpay_env

# Activate virtual environment (do this every time you work)
source syncpay_env/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the cluster
chmod +x run_cluster.sh
./run_cluster.sh

# Run tests
python test_payments.py
```

## API Endpoints
- POST /payment - Process a payment
- GET /transactions - Get all transactions  
- GET /health - Health check
- GET /status - Node status
