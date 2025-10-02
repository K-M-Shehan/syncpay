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
from utils.metrics import MetricsCollector

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
        
        # Get logger after setting up logging
        self.logger = logging.getLogger(f"SyncPayNode-{node_id}")
        
        # Initialize Flask app
        self.app = Flask(__name__)
        
        # Storage for transactions (in-memory for demo)
        self.transactions = {}
        self.transaction_log = []
        self._transaction_lock = threading.Lock()  # Thread-safe access to transactions
        
        # Initialize metrics collector
        self.metrics = MetricsCollector(node_id)
        
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
            # Start timer for request processing
            timer_id = self.metrics.start_timer('payment_request')
            self.metrics.increment('payment_requests_total')
            
            try:
                data = request.json
                
                # Validate input
                if not data:
                    self.metrics.increment('payment_errors_validation')
                    return jsonify({"error": "Request body is required"}), 400
                
                if not all(k in data for k in ['amount', 'sender', 'receiver']):
                    self.metrics.increment('payment_errors_validation')
                    return jsonify({"error": "Missing required fields: amount, sender, receiver"}), 400
                
                # Validate amount
                try:
                    amount = float(data['amount'])
                    if amount <= 0:
                        return jsonify({"error": "Amount must be positive"}), 400
                    if amount > 1000000:  # Reasonable upper limit
                        return jsonify({"error": "Amount exceeds maximum limit"}), 400
                except (ValueError, TypeError):
                    return jsonify({"error": "Invalid amount format"}), 400
                
                # Validate sender and receiver
                sender = str(data['sender']).strip()
                receiver = str(data['receiver']).strip()
                
                if not sender or not receiver:
                    return jsonify({"error": "Sender and receiver cannot be empty"}), 400
                
                if sender == receiver:
                    return jsonify({"error": "Sender and receiver cannot be the same"}), 400
                
                if len(sender) > 100 or len(receiver) > 100:
                    return jsonify({"error": "Sender/receiver names too long"}), 400
                
                # Check if this node can process payments
                if not self.consensus.is_leader():
                    self.metrics.increment('payment_errors_not_leader')
                    return jsonify({
                        "error": "Not leader - cannot process payments",
                        "leader": self.consensus.current_leader
                    }), 503
                
                # Create transaction with synchronized timestamp
                transaction = PaymentTransaction.create(
                    amount=amount,
                    sender=sender,
                    receiver=receiver, 
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
                
                # Record success metrics
                self.metrics.increment('payment_success')
                self.metrics.record_value('payment_amount', amount)
                duration = self.metrics.stop_timer(timer_id)
                
                return jsonify({
                    "status": "success",
                    "transaction_id": transaction.id,
                    "timestamp": transaction.timestamp,
                    "amount": amount,
                    "sender": sender,
                    "receiver": receiver,
                    "processed_by": self.node_id
                })
                
            except ValueError as e:
                self.metrics.increment('payment_errors_validation')
                self.metrics.stop_timer(timer_id)
                return jsonify({"error": f"Validation error: {str(e)}"}), 400
            except TimeoutError as e:
                self.metrics.increment('payment_errors_timeout')
                self.metrics.stop_timer(timer_id)
                return jsonify({"error": "Request timeout", "details": str(e)}), 504
            except Exception as e:
                self.metrics.increment('payment_errors_internal')
                self.metrics.stop_timer(timer_id)
                self.logger.error(f"Error processing payment: {e}", exc_info=True)
                return jsonify({"error": "Internal server error", "details": str(e)}), 500
        
        @self.app.route('/health', methods=['GET'])
        def get_health():
            # Update metrics gauges
            self.metrics.set_gauge('transaction_count', len(self.transactions))
            self.metrics.set_gauge('is_leader', 1 if self.consensus.is_leader() else 0)
            
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
        
        @self.app.route('/metrics', methods=['GET'])
        def get_metrics():
            """Get system metrics"""
            format_type = request.args.get('format', 'json')
            
            if format_type == 'summary':
                return self.metrics.get_summary(), 200, {'Content-Type': 'text/plain'}
            else:
                return jsonify(self.metrics.get_all_metrics())
        
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
        
        try:
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
        except KeyboardInterrupt:
            print(f"\n\nShutting down {self.node_id} gracefully...")
            self.stop()
        except Exception as e:
            print(f"Error starting node: {e}")
            self.stop()
            raise
    
    def stop(self):
        """Stop all services gracefully"""
        try:
            print(f"Stopping {self.node_id} services...")
            self.health_monitor.stop()
            self.replicator.stop()
            self.time_sync.stop()
            self.consensus.stop()
            if hasattr(self.deduplication_manager, 'stop'):
                self.deduplication_manager.stop()
            print(f"{self.node_id} stopped successfully")
        except Exception as e:
            print(f"Error during shutdown: {e}")

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
