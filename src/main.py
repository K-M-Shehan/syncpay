from flask import Flask, request, jsonify
import time
import uuid
import threading
import sys
import os
import logging
from logging.handlers import RotatingFileHandler
from models import PaymentTransaction, NodeInfo
from config import Config

# Import component modules (each member implements their part)
from fault_tolerance.health_monitor import HealthMonitor
from replication.replicator import PaymentReplicator  
from time_sync.time_synchronizer import TimeSynchronizer
from consensus.raft_consensus import RaftConsensus

class SyncPayNode:
    def __init__(self, node_id: str, config_file: str = None):
        self.node_id = node_id
        self.config = Config(config_file)
        self.node_config = self.config.node_configs[node_id]
        self._setup_logging()
        
        # Initialize Flask app
        self.app = Flask(__name__)
        
        # Storage for transactions (in-memory for demo)
        self.transactions = {}
        self.transaction_log = []
        self._transaction_lock = threading.Lock()  # Thread-safe access to transactions
        
        # Initialize components (each member's responsibility)
        self.health_monitor = HealthMonitor(self)      # Member 1
        self.replicator = PaymentReplicator(self)      # Member 2  
        self.time_sync = TimeSynchronizer(self)        # Member 3
        self.consensus = RaftConsensus(self)           # Member 4
        
        # Initialize deduplication manager (optional component)
        from replication.deduplication import DeduplicationManager
        self.deduplication_manager = DeduplicationManager(self)
        
        # Setup routes
        self.setup_routes()

    def _setup_logging(self):
        """Configure logging to file to avoid blocking stdout/stderr pipes"""
        try:
            # Determine logs directory at project root
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
            logs_dir = os.path.join(base_dir, 'logs')
            os.makedirs(logs_dir, exist_ok=True)

            log_path = os.path.join(logs_dir, f"{self.node_id}.log")

            # Reset root handlers to avoid duplicate logs
            root_logger = logging.getLogger()
            for h in list(root_logger.handlers):
                root_logger.removeHandler(h)

            handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3)
            formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
            handler.setFormatter(formatter)

            root_logger.addHandler(handler)
            root_logger.setLevel(logging.INFO)

            # Reduce noisy loggers
            logging.getLogger('werkzeug').setLevel(logging.WARNING)
        except Exception as e:
            # As a fallback, at least ensure logging is configured
            logging.basicConfig(level=logging.INFO)
        
    def setup_routes(self):
        @self.app.route('/payment', methods=['POST'])
        def process_payment():
            try:
                data = request.json
                
                # Validate input
                if not all(k in data for k in ['amount', 'sender', 'receiver']):
                    return jsonify({"error": "Missing required fields"}), 400
                
                # Check if this node can process payments
                if not self.consensus.is_leader():
                    return jsonify({"error": "Not leader - cannot process payments"}), 503
                
                # Create transaction with synchronized timestamp
                transaction = PaymentTransaction.create(
                    amount=float(data['amount']),
                    sender=data['sender'],
                    receiver=data['receiver'], 
                    node_id=self.node_id
                )
                
                # Apply time synchronization (Member 3)
                transaction.timestamp = self.time_sync.get_synchronized_time()
                
                # Try to achieve consensus with timeout (Member 4)
                import threading
                import queue
                
                consensus_result = queue.Queue()
                
                def try_consensus():
                    try:
                        result = self.consensus.propose_transaction(transaction)
                        consensus_result.put(('success', result))
                    except Exception as e:
                        consensus_result.put(('error', str(e)))
                
                # Run consensus in a separate thread with timeout
                consensus_thread = threading.Thread(target=try_consensus)
                consensus_thread.daemon = True
                consensus_thread.start()
                consensus_thread.join(timeout=5.0)  # Allow more time for consensus
                
                if consensus_thread.is_alive():
                    return jsonify({"error": "Consensus timeout"}), 504
                
                try:
                    result_type, result = consensus_result.get_nowait()
                    if result_type == 'error':
                        return jsonify({"error": f"Consensus error: {result}"}), 500
                    elif not result:
                        return jsonify({"error": "Consensus failed"}), 500
                except queue.Empty:
                    return jsonify({"error": "Consensus timeout"}), 504
                
                # Store transaction locally
                with self._transaction_lock:
                    self.transactions[transaction.id] = transaction
                    self.transaction_log.append(transaction)
                
                # Replicate to other nodes (Member 2) - don't wait for this
                threading.Thread(
                    target=self.replicator.replicate_transaction, 
                    args=(transaction,), 
                    daemon=True
                ).start()
                
                # Mark as confirmed
                transaction.status = "confirmed"
                
                return jsonify({
                    "status": "success",
                    "transaction_id": transaction.id,
                    "timestamp": transaction.timestamp,
                    "processed_by": self.node_id
                })
                
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/health', methods=['GET'])
        def get_health():
            return jsonify({
                "node_id": self.node_id,
                "status": "healthy",
                "is_leader": self.consensus.is_leader(),
                "timestamp": self.time_sync.get_synchronized_time(),
                "transaction_count": len(self.transactions)
            })
        
        @self.app.route('/ping', methods=['GET'])
        def ping():
            # Simple ping endpoint for testing connectivity
            return jsonify({"status": "ok", "node_id": self.node_id})
        
        @self.app.route('/transactions', methods=['GET'])
        def get_transactions():
            # Return transactions sorted by synchronized timestamp
            with self._transaction_lock:
                sorted_transactions = sorted(
                    [t.to_dict() for t in self.transactions.values()],
                    key=lambda x: x['timestamp']
                )
            return jsonify({
                "transactions": sorted_transactions,
                "total_count": len(sorted_transactions),
                "node_id": self.node_id
            })
        
        @self.app.route('/status', methods=['GET'])
        def get_status():
            return jsonify({
                "node_id": self.node_id,
                "is_leader": self.consensus.is_leader(),
                "peer_health": self.health_monitor.get_peer_status(),
                "replication_status": self.replicator.get_replication_status(),
                "time_offset": self.time_sync.get_time_offset()
            })
        
        # Internal endpoints for component communication
        @self.app.route('/replicate', methods=['POST'])
        def handle_replication():
            response_data, status_code = self.replicator.handle_replication_request(request)
            return jsonify(response_data), status_code
        
        @self.app.route('/replicate/batch', methods=['POST'])
        def handle_batch_replication():
            response_data, status_code = self.replicator.handle_batch_replication_request(request)
            return jsonify(response_data), status_code
        
        @self.app.route('/consensus', methods=['POST'])
        def handle_consensus():
            response_data, status_code = self.consensus.handle_consensus_request(request)
            return jsonify(response_data), status_code
        
        @self.app.route('/time_sync', methods=['POST'])  
        def handle_time_sync():
            response_data, status_code = self.time_sync.handle_sync_request(request)
            return jsonify(response_data), status_code
    
    def start(self):
        """Start all background services and the Flask server"""
        print(f"Starting SyncPay Node: {self.node_id}")
        
        # Start component services
        self.health_monitor.start()     # Member 1: Start health monitoring
        self.replicator.start()         # Member 2: Start replication service
        self.time_sync.start()          # Member 3: Start time synchronization
        self.consensus.start()          # Member 4: Start consensus protocol
        self.deduplication_manager.start()  # Start deduplication service
        
        # Start Flask server
        host = self.node_config['host']
        port = self.node_config['port']
        print(f"SyncPay node {self.node_id} running on {host}:{port}")
        
        self.app.run(host=host, port=port, debug=False, threaded=True)

def main():
    if len(sys.argv) != 2:
        print("Usage: python main.py <node_id>")
        print("Available nodes: node1, node2, node3")
        sys.exit(1)
    
    node_id = sys.argv[1]
    
    # Validate node_id
    config = Config()
    if node_id not in config.node_configs:
        print(f"Invalid node_id: {node_id}")
        print(f"Available nodes: {list(config.node_configs.keys())}")
        sys.exit(1)
    
    # Start the SyncPay node
    node = SyncPayNode(node_id)
    node.start()

if __name__ == "__main__":
    main()
