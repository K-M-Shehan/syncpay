# src/replication/replicator.py
# Member 2: Payment Replication Component

import time
import threading
import requests
import json
from typing import Dict, List, Optional, Any
from collections import defaultdict, deque
import logging
from datetime import datetime

class PaymentReplicator:
    def __init__(self, node):
        self.node = node

        # Replication state
        self.replication_status = {}  # peer -> status dict
        self.pending_replications = defaultdict(deque)  # peer -> queue of transactions
        self.replication_lock = threading.Lock()

        # Worker threads
        self.worker_threads = []
        self.num_workers = 3  # Number of async replication workers
        self.is_running = False

        # Configuration
        self.replication_timeout = 5.0  # seconds
        self.max_retry_attempts = 3
        self.retry_delay = 1.0  # seconds
        self.batch_size = 10  # Max transactions per batch

        # Metrics
        self.replication_stats = {
            'total_sent': 0,
            'total_successful': 0,
            'total_failed': 0,
            'avg_response_time': 0.0,
            'last_replication_time': 0.0
        }

        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(f"Replicator-{node.node_id}")

    def start(self):
        """Start the replication service"""
        if self.is_running:
            return

        self.is_running = True
        self.logger.info("Starting payment replication service")

        # Initialize replication status for all peers
        peers = self.node.config.get_peers(self.node.node_id)
        for peer in peers:
            self.replication_status[peer] = {
                'is_connected': True,
                'pending_count': 0,
                'last_successful_replication': time.time(),
                'last_attempt': 0.0,
                'consecutive_failures': 0,
                'total_replications': 0,
                'successful_replications': 0
            }

        # Start worker threads for async replication
        for i in range(self.num_workers):
            worker = threading.Thread(
                target=self._replication_worker,
                args=(i,),
                daemon=True,
                name=f"ReplicationWorker-{i}"
            )
            worker.start()
            self.worker_threads.append(worker)

        self.logger.info(f"Started {self.num_workers} replication worker threads")

    def stop(self):
        """Stop the replication service"""
        self.is_running = False
        self.logger.info("Stopping payment replication service")

        # Wait for worker threads to finish
        for worker in self.worker_threads:
            worker.join(timeout=5.0)

        self.worker_threads.clear()

    def replicate_transaction(self, transaction):
        """
        Replicate a transaction to all peer nodes
        This is the main entry point for transaction replication
        """
        peers = self.node.config.get_peers(self.node.node_id)

        if not peers:
            self.logger.warning("No peers configured for replication")
            return

        self.logger.info(f"Replicating transaction {transaction.id} to {len(peers)} peers")

        # Queue transaction for async replication to all peers
        for peer in peers:
            with self.replication_lock:
                self.pending_replications[peer].append(transaction)
                self.replication_status[peer]['pending_count'] += 1

        # Update metrics
        self.replication_stats['total_sent'] += len(peers)
        self.replication_stats['last_replication_time'] = time.time()

    def _replication_worker(self, worker_id: int):
        """Worker thread for processing replication queue"""
        self.logger.debug(f"Replication worker {worker_id} started")

        while self.is_running:
            try:
                # Get next transaction to replicate
                transaction = None
                target_peer = None

                with self.replication_lock:
                    # Find a peer with pending transactions
                    for peer, queue in self.pending_replications.items():
                        if queue:
                            transaction = queue.popleft()
                            self.replication_status[peer]['pending_count'] -= 1
                            target_peer = peer
                            break

                if transaction and target_peer:
                    self._replicate_to_peer(target_peer, transaction)
                else:
                    # No work to do, sleep briefly
                    time.sleep(0.1)

            except Exception as e:
                self.logger.error(f"Error in replication worker {worker_id}: {e}")
                time.sleep(1.0)

        self.logger.debug(f"Replication worker {worker_id} stopped")

    def _replicate_to_peer(self, peer: str, transaction):
        """Replicate a single transaction to a specific peer"""
        start_time = time.time()
        success = False

        try:
            # Send replication request
            success = self._send_replication_request(peer, transaction, sync=False)

        except Exception as e:
            self.logger.error(f"Failed to replicate transaction {transaction.id} to {peer}: {e}")

        finally:
            # Update peer status
            with self.replication_lock:
                status = self.replication_status[peer]
                status['last_attempt'] = time.time()
                status['total_replications'] += 1

                if success:
                    status['last_successful_replication'] = time.time()
                    status['consecutive_failures'] = 0
                    status['successful_replications'] += 1
                    self.replication_stats['total_successful'] += 1
                else:
                    status['consecutive_failures'] += 1
                    self.replication_stats['total_failed'] += 1

            # Update response time metric
            response_time = time.time() - start_time
            self._update_response_time_metric(response_time)

    def _send_replication_request(self, peer: str, transaction, sync: bool = False) -> bool:
        """
        Send a replication request to a peer
        Returns True if successful, False otherwise
        """
        url = f"http://{peer}/replicate"
        payload = {
            'transaction': transaction.to_dict(),
            'source_node': self.node.node_id,
            'timestamp': time.time()
        }

        for attempt in range(self.max_retry_attempts):
            try:
                response = requests.post(
                    url,
                    json=payload,
                    timeout=self.replication_timeout,
                    headers={'Content-Type': 'application/json'}
                )

                if response.status_code == 200:
                    response_data = response.json()
                    status = response_data.get('status')
                    if status == 'success':
                        self.logger.debug(f"Successfully replicated transaction {transaction.id} to {peer}")
                        return True
                    elif status == 'duplicate' or status == 'already_exists':
                        self.logger.debug(f"Transaction {transaction.id} already exists on {peer}")
                        return True  # Treat duplicates as success
                    else:
                        self.logger.warning(f"Replication rejected by {peer}: {response_data.get('error', 'unknown error')}")
                        return False
                else:
                    self.logger.warning(f"Replication failed to {peer}: HTTP {response.status_code}")

            except requests.exceptions.Timeout:
                self.logger.warning(f"Replication timeout to {peer} (attempt {attempt + 1}/{self.max_retry_attempts})")
            except requests.exceptions.ConnectionError:
                self.logger.warning(f"Connection error replicating to {peer} (attempt {attempt + 1}/{self.max_retry_attempts})")
            except Exception as e:
                self.logger.error(f"Unexpected error replicating to {peer}: {e}")

            # Wait before retry
            if attempt < self.max_retry_attempts - 1:
                time.sleep(self.retry_delay * (attempt + 1))  # Exponential backoff

        return False

    def handle_replication_request(self, request) -> tuple[Dict[str, Any], int]:
        """
        Handle incoming replication requests from other nodes
        Returns (response_dict, status_code)
        """
        try:
            data = request.get_json()

            if not data or 'transaction' not in data:
                return {"error": "Missing transaction data"}, 400

            transaction_data = data['transaction']
            source_node = data.get('source_node', 'unknown')

            # Validate transaction data
            required_fields = ['id', 'amount', 'sender', 'receiver', 'timestamp', 'status', 'node_id']
            if not all(field in transaction_data for field in required_fields):
                return {"error": "Invalid transaction data"}, 400

            # Create transaction object
            transaction = self._dict_to_transaction(transaction_data)

            # Check for duplicates using deduplication manager
            if hasattr(self.node, 'deduplication_manager'):
                is_duplicate, original_id = self.node.deduplication_manager.is_duplicate_transaction(transaction)
                if is_duplicate:
                    self.logger.info(f"Rejected duplicate transaction {transaction.id} from {source_node}")
                    return {
                        "status": "duplicate",
                        "original_transaction_id": original_id
                    }, 200

            # Store transaction locally
            # Use threading lock instead of consensus lock for transaction storage
            import threading
            if not hasattr(self.node, '_transaction_lock'):
                self.node._transaction_lock = threading.Lock()
                
            with self.node._transaction_lock:  # Ensure thread safety
                if transaction.id not in self.node.transactions:
                    self.node.transactions[transaction.id] = transaction
                    self.node.transaction_log.append(transaction)

                    # Register with deduplication manager
                    if hasattr(self.node, 'deduplication_manager'):
                        self.node.deduplication_manager.register_transaction(transaction)

                    self.logger.info(f"Successfully replicated transaction {transaction.id} from {source_node}")
                    return {"status": "success", "transaction_id": transaction.id}, 200
                else:
                    # Transaction already exists
                    self.logger.debug(f"Transaction {transaction.id} already exists")
                    return {"status": "already_exists", "transaction_id": transaction.id}, 200

        except Exception as e:
            self.logger.error(f"Error handling replication request: {e}")
            return {"error": str(e)}, 500

    def handle_batch_replication_request(self, request) -> tuple[Dict[str, Any], int]:
        """
        Handle incoming batch replication requests for sync operations
        Returns (response_dict, status_code)
        """
        try:
            data = request.get_json()

            if not data or 'transactions' not in data:
                return {"error": "Missing transactions data"}, 400

            transactions_data = data['transactions']
            source_node = data.get('source_node', 'unknown')
            is_sync = data.get('is_sync', False)

            successful_count = 0
            failed_count = 0
            errors = []

            for txn_data in transactions_data:
                try:
                    # Create transaction object
                    transaction = self._dict_to_transaction(txn_data)

                    # Check for duplicates
                    if hasattr(self.node, 'deduplication_manager'):
                        is_duplicate, original_id = self.node.deduplication_manager.is_duplicate_transaction(transaction)
                        if is_duplicate and not is_sync:
                            continue  # Skip duplicates in normal operation

                    # Store transaction locally
                    import threading
                    if not hasattr(self.node, '_transaction_lock'):
                        self.node._transaction_lock = threading.Lock()
                        
                    with self.node._transaction_lock:
                        if transaction.id not in self.node.transactions:
                            self.node.transactions[transaction.id] = transaction
                            self.node.transaction_log.append(transaction)

                            # Register with deduplication manager
                            if hasattr(self.node, 'deduplication_manager'):
                                self.node.deduplication_manager.register_transaction(transaction)

                            successful_count += 1
                        else:
                            successful_count += 1  # Already exists, consider successful

                except Exception as e:
                    failed_count += 1
                    errors.append(f"Transaction {txn_data.get('id', 'unknown')}: {str(e)}")

            self.logger.info(f"Batch replication from {source_node}: {successful_count}/{len(transactions_data)} successful")

            return {
                "status": "completed",
                "successful_count": successful_count,
                "failed_count": failed_count,
                "total_count": len(transactions_data),
                "errors": errors
            }, 200

        except Exception as e:
            self.logger.error(f"Error handling batch replication request: {e}")
            return {"error": str(e)}, 500

    def _dict_to_transaction(self, data: Dict) -> Any:
        """Convert dictionary to PaymentTransaction object"""
        # Import here to avoid circular imports
        from models import PaymentTransaction

        return PaymentTransaction(
            id=data['id'],
            amount=data['amount'],
            sender=data['sender'],
            receiver=data['receiver'],
            timestamp=data['timestamp'],
            status=data['status'],
            node_id=data['node_id']
        )

    def sync_with_recovered_peer(self, peer_url: str):
        """Sync all transactions with a recovered peer"""
        self.logger.info(f"Syncing all transactions with recovered peer {peer_url}")

        # Get all transactions
        transactions = list(self.node.transactions.values())

        if not transactions:
            self.logger.info("No transactions to sync")
            return

        # Sort by timestamp for consistent ordering
        transactions.sort(key=lambda t: t.timestamp)

        # Send transactions in batches
        batch_size = self.batch_size
        for i in range(0, len(transactions), batch_size):
            batch = transactions[i:i + batch_size]

            if not self._sync_batch_with_peer(peer_url, batch):
                self.logger.error(f"Failed to sync batch with {peer_url}, stopping sync")
                break

        self.logger.info(f"Completed sync with recovered peer {peer_url}")

    def _sync_batch_with_peer(self, peer: str, transactions: List) -> bool:
        """Sync a batch of transactions with a peer"""
        url = f"http://{peer}/replicate/batch"
        payload = {
            'transactions': [t.to_dict() for t in transactions],
            'source_node': self.node.node_id,
            'timestamp': time.time(),
            'is_sync': True
        }

        try:
            response = requests.post(
                url,
                json=payload,
                timeout=self.replication_timeout * 2,  # Longer timeout for batch
                headers={'Content-Type': 'application/json'}
            )

            if response.status_code == 200:
                response_data = response.json()
                successful = response_data.get('successful_count', 0)
                total = len(transactions)
                self.logger.debug(f"Batch sync to {peer}: {successful}/{total} transactions")
                return successful == total
            else:
                self.logger.warning(f"Batch sync failed to {peer}: HTTP {response.status_code}")
                return False

        except Exception as e:
            self.logger.error(f"Error during batch sync to {peer}: {e}")
            return False

    def handle_peer_failure(self, peer_url: str):
        """Handle peer failure - mark as disconnected and clear pending replications"""
        self.logger.warning(f"Handling peer failure: {peer_url}")

        with self.replication_lock:
            if peer_url in self.replication_status:
                self.replication_status[peer_url]['is_connected'] = False

                # Clear pending replications for failed peer
                if peer_url in self.pending_replications:
                    pending_count = len(self.pending_replications[peer_url])
                    if pending_count > 0:
                        self.pending_replications[peer_url].clear()
                        self.replication_status[peer_url]['pending_count'] = 0
                        self.logger.info(f"Cleared {pending_count} pending replications for failed peer {peer_url}")

    def handle_peer_recovery(self, peer_url: str):
        """Handle peer recovery - mark as connected"""
        self.logger.info(f"Handling peer recovery: {peer_url}")

        with self.replication_lock:
            if peer_url in self.replication_status:
                self.replication_status[peer_url]['is_connected'] = True
                self.replication_status[peer_url]['consecutive_failures'] = 0

    def get_replication_status(self) -> Dict:
        """Get current replication status for all peers"""
        with self.replication_lock:
            status = {}
            for peer, peer_status in self.replication_status.items():
                status[peer] = {
                    'connected': peer_status['is_connected'],
                    'pending_count': peer_status['pending_count'],
                    'last_successful_replication': peer_status['last_successful_replication'],
                    'consecutive_failures': peer_status['consecutive_failures'],
                    'success_rate': (peer_status['successful_replications'] /
                                   max(peer_status['total_replications'], 1))
                }
            return status

    def get_replication_metrics(self) -> Dict:
        """Get detailed replication metrics"""
        with self.replication_lock:
            current_time = time.time()

            return {
                'total_sent': self.replication_stats['total_sent'],
                'total_successful': self.replication_stats['total_successful'],
                'total_failed': self.replication_stats['total_failed'],
                'success_rate': (self.replication_stats['total_successful'] /
                               max(self.replication_stats['total_sent'], 1)),
                'avg_response_time': self.replication_stats['avg_response_time'],
                'last_replication_time': self.replication_stats['last_replication_time'],
                'time_since_last_replication': current_time - self.replication_stats['last_replication_time'],
                'peer_status': self.get_replication_status(),
                'active_workers': len([t for t in self.worker_threads if t.is_alive()]),
                'total_pending': sum(len(queue) for queue in self.pending_replications.values())
            }

    def _update_response_time_metric(self, response_time: float):
        """Update average response time metric"""
        # Simple exponential moving average
        alpha = 0.1
        self.replication_stats['avg_response_time'] = (
            alpha * response_time +
            (1 - alpha) * self.replication_stats['avg_response_time']
        )

    def force_sync_all_peers(self):
        """Force synchronization of all transactions with all peers"""
        self.logger.info("Forcing sync of all transactions with all peers")

        peers = self.node.config.get_peers(self.node.node_id)
        transactions = list(self.node.transactions.values())

        if not transactions or not peers:
            return

        for peer in peers:
            self.sync_with_recovered_peer(peer)