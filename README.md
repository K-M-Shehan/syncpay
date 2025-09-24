# syncpay
> a distributed payment processing system

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/Flask-2.3+-green.svg)](https://flask.palletsprojects.com/)
[![Tests](https://img.shields.io/badge/Tests-38%20passing-success.svg)](./tests/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-brightgreen.svg)]()

## 📋 Table of Contents

| Section | Description |
|---------|-------------|
| [🌟 Overview](#-overview) | System introduction and core concepts |
| [🏗️ Architecture](#️-architecture) | System architecture and components |
| [🚀 Quick Start](#-quick-start) | Get up and running in minutes |
| [🎬 Demo Options](#-demo-options) | Interactive demonstrations |
| [🧪 Testing](#-testing) | Test suite and validation |
| [📖 API Reference](#-api-reference) | Complete API documentation |
| [🏛️ System Design](#️-system-design) | Design principles and patterns |
| [🔧 Development](#-development) | Development setup and guidelines |
| [📊 Implementation Details](#-implementation-details) | Performance and scalability |
| [🤝 Contributing](#-contributing) | How to contribute |

## 🌟 Overview

SyncPay is a production-ready distributed payment processing system that demonstrates advanced distributed systems concepts. Built with Python and Flask, it provides a robust foundation for understanding and implementing distributed consensus, fault tolerance, and data consistency in payment systems.

**🎯 Purpose:** Educational and production-ready implementation of core distributed systems patterns for payment processing.

**🔧 Built With:** Python 3.11+, Flask 2.3+, Threading, Pytest - leveraging modern async patterns and comprehensive testing.

### ✨ Key Features

- 🏆 **Raft Consensus** - Leader election and distributed agreement
- 🔄 **Data Replication** - Automatic replication with deduplication
- ⏰ **Time Synchronization** - NTP-style clock synchronization
- 🛡️ **Fault Tolerance** - Health monitoring and automatic failover
- 🧪 **Comprehensive Testing** - 38 unit and integration tests
- 🎬 **Interactive Demos** - Multiple demo modes for exploration

### 🎯 Use Cases

- **E-commerce Platforms** - Process payments across multiple servers
- **Financial Systems** - Ensure transaction consistency and availability  
- **Distributed Systems Learning** - Understand consensus and replication patterns
- **Production Deployment** - Scale payment processing horizontally

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SyncPay Cluster                         │
├─────────────┬─────────────┬─────────────────────────────────┤
│    Node 1   │    Node 2   │         Node 3                  │
│   (Leader)  │ (Follower)  │      (Follower)                 │
├─────────────┼─────────────┼─────────────────────────────────┤
│ • Consensus │ • Consensus │ • Consensus                     │
│ • Replicator│ • Replicator│ • Replicator                    │
│ • Time Sync │ • Time Sync │ • Time Sync                     │
│ • Health Mon│ • Health Mon│ • Health Monitor                │
└─────────────┴─────────────┴─────────────────────────────────┘
         │             │               │
         └─────────────┼───────────────┘
                       │
              ┌─────────▼─────────┐
              │   Client Apps     │
              │ (Payment Requests)│
              └───────────────────┘
```

### Core Components

1. **Fault Tolerance** - Health monitoring, failure detection, automatic failover
2. **Data Replication** - Primary-backup replication with strong consistency  
3. **Time Synchronization** - NTP-style algorithm with drift correction
4. **Consensus Algorithm** - Raft implementation for distributed agreement

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Git

### Installation

```bash
# Clone the repository
git clone https://github.com/K-M-Shehan/syncpay.git
cd syncpay

# Create virtual environment
python3 -m venv syncpay_env
source syncpay_env/bin/activate  # On Windows: syncpay_env\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Run Demo

```bash
# Quick 30-second demo
./quick_demo.sh

# Interactive demo (recommended)
./run_cluster.sh
```

## 🎬 Demo Options

### 1. 🎯 Interactive Demo (Recommended)
```bash
./run_cluster.sh
```
**Features:**
- Interactive menu system
- Real-time cluster monitoring
- Payment processing tests
- Stress testing capabilities
- Fault tolerance demonstration

**Menu Options:**
- `1` - Run payment test
- `2` - Run stress test (5 concurrent payments)
- `3` - Demo fault tolerance (kill/restart nodes)
- `s` - Show cluster status
- `l` - View live logs
- `q` - Quit

### 2. ⚡ Quick Demo
```bash
./quick_demo.sh
```
**Features:**
- 30-second automated demonstration
- Shows all core functionality
- Perfect for presentations

### 3. 🤖 Automated Full Demo
```bash
./run_cluster.sh auto
```
**Features:**
- Complete automated test suite
- Payment processing
- Stress testing
- Fault tolerance scenarios

### 4. 🔬 Single Test
```bash
./run_cluster.sh test
```
**Features:**
- Quick functionality verification
- Single payment test
- Immediate results

### 5. 🛑 Stop Cluster
```bash
./stop_cluster.sh
```
**Features:**
- Clean shutdown of all nodes
- Process cleanup
- Log preservation

## 🧪 Testing

### Unit & Integration Tests
```bash
# Run all tests (38 tests)
python -m pytest tests/ -v

# Run specific test suites
python -m pytest tests/test_payment_replicator.py -v
python -m pytest tests/test_time_synchronizer.py -v
python -m pytest tests/test_raft_consensus.py -v
python -m pytest tests/test_integration.py -v
```

### End-to-End Tests
```bash
# Run with real HTTP servers
python tests/test_end_to_end.py --e2e
```

### Functional Tests
```bash
# Debug and inspect system
python debug_test.py

# Simple functionality test
python simple_test.py
```

## 📚 API Reference

### Payment Endpoints

#### Process Payment
```http
POST /payment
Content-Type: application/json

{
  "amount": 150.75,
  "sender": "alice",
  "receiver": "bob"
}
```

**Response:**
```json
{
  "status": "success",
  "transaction_id": "txn_abc123",
  "timestamp": 1727123456.789,
  "amount": 150.75,
  "sender": "alice",
  "receiver": "bob",
  "processed_by": "node1"
}
```

#### Get Transactions
```http
GET /transactions
```

**Response:**
```json
{
  "transactions": [...],
  "total_count": 42,
  "node_id": "node1"
}
```

### System Endpoints

#### Health Check
```http
GET /health
```

**Response:**
```json
{
  "node_id": "node1",
  "status": "healthy",
  "is_leader": true,
  "timestamp": 1727123456.789,
  "transaction_count": 42
}
```

#### Node Status
```http
GET /status
```

**Response:**
```json
{
  "node_id": "node1",
  "is_leader": true,
  "peer_health": {...},
  "replication_status": {...},
  "time_offset": 0.001
}
```

#### Simple Ping
```http
GET /ping
```

**Response:**
```json
{
  "status": "ok",
  "node_id": "node1"
}
```

## 🏛️ System Design

### Distributed Systems Principles

**CAP Theorem Trade-offs:**
- **Consistency**: Strong consistency through Raft consensus
- **Availability**: High availability with leader election and failover
- **Partition Tolerance**: Handles network partitions gracefully

**ACID Properties:**
- **Atomicity**: All-or-nothing transaction processing
- **Consistency**: Maintains data integrity across nodes
- **Isolation**: Concurrent transactions don't interfere
- **Durability**: Committed transactions survive failures

### Component Architecture

#### 1. Fault Tolerance (HealthMonitor)
```
📊 Health Monitoring
├── Peer Discovery
├── Failure Detection (heartbeats)
├── Automatic Failover
└── Recovery Handling
```

**Key Features:**
- Continuous health monitoring of peer nodes
- Configurable failure thresholds
- Automatic leader failover
- Graceful node recovery

#### 2. Data Replication (PaymentReplicator)
```
🔄 Replication System
├── Async Worker Threads
├── Batch Replication
├── Deduplication Manager
└── Consistency Manager
```

**Key Features:**
- Asynchronous replication workers
- Content-based deduplication
- Batch processing for efficiency
- Strong consistency guarantees

#### 3. Time Synchronization (TimeSynchronizer)
```
⏰ Time Management
├── NTP-style Algorithm
├── Outlier Detection
├── Statistical Filtering
└── Drift Correction
```

**Key Features:**
- Network Time Protocol simulation
- Clock skew detection and correction
- Statistical outlier filtering
- Sub-second accuracy

#### 4. Consensus (RaftConsensus)
```
🏆 Raft Algorithm
├── Leader Election
├── Log Replication
├── Term Management
└── Majority Voting
```

**Key Features:**
- Complete Raft consensus implementation
- Dynamic leader election
- Log replication with majority agreement
- Split-brain prevention

## 🔧 Development

### Project Structure

```
syncpay/
├── 📁 src/                     # Core implementation
│   ├── main.py                 # SyncPayNode + Flask server
│   ├── config.py               # Configuration management
│   ├── models.py               # Data models
│   ├── 📁 consensus/           # Raft consensus
│   ├── 📁 fault_tolerance/     # Health monitoring
│   ├── 📁 replication/         # Data replication
│   ├── 📁 time_sync/           # Time synchronization
│   └── 📁 utils/               # Utility functions
├── 📁 tests/                   # Test suite (38 tests)
│   ├── test_payment_replicator.py
│   ├── test_time_synchronizer.py
│   ├── test_raft_consensus.py
│   ├── test_integration.py
│   └── test_end_to_end.py
├── 📁 logs/                    # Runtime logs
├── 📁 configs/                 # Configuration files
├── 📁 docs/                    # Documentation
├── 🎬 run_cluster.sh           # Interactive demo
├── ⚡ quick_demo.sh            # Quick demo
├── 🛑 stop_cluster.sh          # Clean shutdown
└── 📋 requirements.txt         # Dependencies
```

### Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Language** | Python 3.11+ | Core implementation |
| **Web Framework** | Flask 2.3+ | HTTP API and inter-node communication |
| **HTTP Client** | Requests | Node-to-node HTTP requests |
| **Threading** | threading | Concurrent processing |
| **Testing** | pytest | Unit and integration testing |
| **Mocking** | unittest.mock | Test isolation |
| **Time** | time, datetime | Timestamp management |
| **JSON** | json | Data serialization |
| **Hashing** | hashlib | Content deduplication |
| **Logging** | logging | System monitoring |

## 📊 Implementation Details

### Performance Metrics

| Metric | Value | Description |
|--------|-------|-------------|
| **Consensus Timeout** | 2 seconds | Time limit for reaching consensus |
| **Health Check Interval** | 5 seconds | Frequency of peer health checks |
| **Time Sync Interval** | 30 seconds | Time synchronization frequency |
| **Replication Workers** | 3 threads | Concurrent replication capacity |
| **Test Coverage** | 38 tests | Unit and integration test suite |

### Scalability

| Aspect | Current | Scalable To |
|--------|---------|-------------|
| **Nodes** | 3 nodes | 5-7 nodes (Raft optimal) |
| **Transactions/sec** | ~10 TPS | ~100 TPS (with optimization) |
| **Storage** | In-memory | Database backends |
| **Network** | HTTP/REST | gRPC for efficiency |

### Production Readiness

✅ **Implemented:**
- Thread-safe operations
- Error handling and recovery
- Comprehensive logging
- Graceful shutdown
- Configuration management

🚧 **Future Enhancements:**
- Database persistence
- TLS/SSL encryption
- Authentication & authorization
- Metrics and monitoring
- Docker containerization

## 🤝 Contributing

### Development Setup

```bash
# Clone and setup
git clone https://github.com/K-M-Shehan/syncpay.git
cd syncpay
python3 -m venv syncpay_env
source syncpay_env/bin/activate
pip install -r requirements.txt

# Run tests
python -m pytest tests/ -v

# Start development cluster
./run_cluster.sh
```

### Contributing Guidelines

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Write** tests for your changes
4. **Ensure** all tests pass (`python -m pytest tests/ -v`)
5. **Commit** your changes (`git commit -m 'Add amazing feature'`)
6. **Push** to the branch (`git push origin feature/amazing-feature`)
7. **Create** a Pull Request

### Code Style

- Follow PEP 8 style guidelines
- Use meaningful variable names
- Add docstrings to functions and classes
- Include type hints where appropriate
- Maintain test coverage

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Raft Algorithm** - Diego Ongaro and John Ousterhout
- **Distributed Systems Concepts** - Martin Kleppmann's "Designing Data-Intensive Applications"
- **Python Community** - For excellent libraries and tools

---


*SyncPay - Powering the future of distributed payments*1. Fault Tolerance (Member 1):
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

### 🎬 Demo Options

**Option 1: Quick 30-second Demo**
```bash
./quick_demo.sh
```

**Option 2: Interactive Demo (Recommended)**
```bash
./run_cluster.sh
# Then use menu: 1=payment test, 2=stress test, 3=fault tolerance, s=status, q=quit
```

**Option 3: Automated Full Demo**
```bash
./run_cluster.sh auto
```

**Option 4: Single Test**
```bash
./run_cluster.sh test
```

### 🛑 Stop Cluster
```bash
./stop_cluster.sh
```

### 🧪 Manual Testing
```bash
# Create virtual environment (one time only)
python3 -m venv syncpay_env

# Activate virtual environment (do this every time you work)
source syncpay_env/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run comprehensive tests
python -m pytest tests/ -v

# Run end-to-end tests with real servers
python tests/test_end_to_end.py --e2e
```

## API Endpoints
- POST /payment - Process a payment
- GET /transactions - Get all transactions  
- GET /health - Health check
- GET /status - Node status