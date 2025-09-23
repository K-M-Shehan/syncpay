# src/replication/deduplication.py
# Member 2: Deduplication Component

import time
import hashlib
from typing import Dict, Set, Optional, List
from collections import defaultdict
import threading
import logging

class DeduplicationManager:
    def __init__(self, node):
        self.node = node
        
        # Deduplication tracking
        self.transaction_hashes = {}      # transaction_id -> content_hash
        self.hash_to_transactions = defaultdict(list)  # content_hash -> [transaction_ids]
        self.processed_transactions = set()  # Set of processed transaction IDs
        self.duplicate_attempts = defaultdict(int)  # Track duplicate attempt counts
        
        # Bloom filter for fast duplicate detection (simplified)
        self.bloom_filter = set()  # In production, use proper bloom filter
        
        # Time-based cleanup
        self.transaction_timestamps = {}  # transaction_id -> timestamp
        self.cleanup_interval = 3600  # Clean up old entries every hour
        self.retention_period = 86400  # Keep dedup records for 24 hours
        
        # Thread safety
        self.dedup_lock = threading.Lock()
        
        # Cleanup thread
        self.cleanup_thread = None
        self.is_running = False
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(f"Deduplication-{node.node_id}")
    
    def start(self):
        """Start the deduplication service"""
        if self.is_running:
            return
            
        self.is_running = True
        self.logger.info("Starting deduplication service")
        
        # Start cleanup thread
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()
    
    def stop(self):
        """Stop the deduplication service"""
        self.is_running = False
        if self.cleanup_thread:
            self.cleanup_thread.join()
        self.logger.info("Deduplication service stopped")
    
    def is_duplicate_transaction(self, transaction) -> tuple[bool, Optional[str]]:
        """
        Check if a transaction is a duplicate
        Returns: (is_duplicate, original_transaction_id)
        """
        with self.dedup_lock:
            # Method 1: Check by transaction ID
            if transaction.id in self.processed_transactions:
                self.duplicate_attempts[transaction.id] += 1
                self.logger.info(f"Duplicate transaction ID detected: {transaction.id}")
                return True, transaction.id
            
            # Method 2: Check by content hash
            content_hash = self._compute_transaction_hash(transaction)
            
            # Quick bloom filter check
            if content_hash in self.bloom_filter:
                # Might be duplicate, check more thoroughly
                if content_hash in self.hash_to_transactions:
                    existing_transactions = self.hash_to_transactions[content_hash]
                    
                    # Check if any existing transaction has the same content
                    for existing_txn_id in existing_transactions:
                        if existing_txn_id != transaction.id:
                            # Found duplicate content with different ID
                            self.duplicate_attempts[existing_txn_id] += 1
                            self.logger.info(f"Duplicate transaction content detected: {transaction.id} matches {existing_txn_id}")
                            return True, existing_txn_id
            
            return False, None
    
    def register_transaction(self, transaction):
        """Register a new transaction in the deduplication system"""
        with self.dedup_lock:
            # Compute and store hash
            content_hash = self._compute_transaction_hash(transaction)
            
            self.transaction_hashes[transaction.id] = content_hash
            self.hash_to_transactions[content_hash].append(transaction.id)
            self.processed_transactions.add(transaction.id)
            self.transaction_timestamps[transaction.id] = time.time()
            
            # Add to bloom filter
            self.bloom_filter.add(content_hash)
            
            self.logger.debug(f"Registered transaction {transaction.id} for deduplication")
    
    def _compute_transaction_hash(self, transaction) -> str:
        """
        Compute a content-based hash for deduplication
        Uses transaction content but excludes ID and timestamp for better duplicate detection
        """
        # Create content string from essential transaction fields
        content = f"{transaction.amount}:{transaction.sender}:{transaction.receiver}"
        
        # Add node_id to handle distributed scenarios
        if hasattr(transaction, 'node_id') and transaction.node_id:
            content += f":{transaction.node_id}"
        
        # Create SHA-256 hash
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def _compute_semantic_hash(self, transaction) -> str:
        """
        Compute semantic hash that's more aggressive in detecting duplicates
        This catches cases like retry attempts with slight variations
        """
        # Normalize amounts (handle floating point precision)
        normalized_amount = f"{float(transaction.amount):.2f}"
        
        # Normalize strings (lowercase, strip whitespace)
        normalized_sender = transaction.sender.lower().strip()
        normalized_receiver = transaction.receiver.lower().strip()
        
        content = f"{normalized_amount}:{normalized_sender}:{normalized_receiver}"
        
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def check_potential_duplicates(self, transaction, time_window: int = 300) -> List[str]:
        """
        Check for potential duplicates within a time window (default 5 minutes)
        Returns list of potentially duplicate transaction IDs
        """
        potential_duplicates = []
        current_time = time.time()
        
        with self.dedup_lock:
            content_hash = self._compute_transaction_hash(transaction)
            semantic_hash = self._compute_semantic_hash(transaction)
            
            # Check for content hash matches
            if content_hash in self.hash_to_transactions:
                for txn_id in self.hash_to_transactions[content_hash]:
                    if txn_id != transaction.id:
                        txn_time = self.transaction_timestamps.get(txn_id, 0)
                        if current_time - txn_time <= time_window:
                            potential_duplicates.append(txn_id)
            
            # Check for semantic hash matches (more aggressive)
            for existing_hash, txn_list in self.hash_to_transactions.items():
                if existing_hash != content_hash:
                    # Check if semantic hashes match
                    for txn_id in txn_list:
                        if txn_id in self.transaction_hashes:
                            existing_txn = self._get_transaction_by_id(txn_id)
                            if existing_txn and self._compute_semantic_hash(existing_txn) == semantic_hash:
                                txn_time = self.transaction_timestamps.get(txn_id, 0)
                                if current_time - txn_time <= time_window:
                                    if txn_id not in potential_duplicates:
                                        potential_duplicates.append(txn_id)
        
        if potential_duplicates:
            self.logger.warning(f"Found {len(potential_duplicates)} potential duplicates for transaction {transaction.id}")
        
        return potential_duplicates
    
    def handle_duplicate_transaction(self, transaction, original_transaction_id: str) -> Dict:
        """
        Handle a detected duplicate transaction
        Returns action taken and details
        """
        action_taken = {
            'action': 'rejected',
            'reason': 'duplicate_detected',
            'original_transaction_id': original_transaction_id,
            'duplicate_transaction_id': transaction.id,
            'timestamp': time.time()
        }
        
        # Log the duplicate attempt
        self.logger.warning(f"Duplicate transaction rejected: {transaction.id} (original: {original_transaction_id})")
        
        # Increment duplicate counter
        with self.dedup_lock:
            self.duplicate_attempts[original_transaction_id] += 1
            
            # If too many duplicates, might indicate a problem
            if self.duplicate_attempts[original_transaction_id] > 10:
                self.logger.error(f"Excessive duplicate attempts for transaction {original_transaction_id}")
                action_taken['warning'] = 'excessive_duplicates'
        
        return action_taken
    
    def _get_transaction_by_id(self, transaction_id: str):
        """Get transaction by ID from the node's transaction store"""
        return self.node.transactions.get(transaction_id)
    
    def get_deduplication_stats(self) -> Dict:
        """Get deduplication statistics"""
        with self.dedup_lock:
            total_transactions = len(self.processed_transactions)
            total_duplicates = sum(self.duplicate_attempts.values())
            unique_duplicated_transactions = len(self.duplicate_attempts)
            
            # Recent duplicates (last hour)
            current_time = time.time()
            recent_duplicates = 0
            for txn_id, attempts in self.duplicate_attempts.items():
                txn_time = self.transaction_timestamps.get(txn_id, 0)
                if current_time - txn_time <= 3600:  # Last hour
                    recent_duplicates += attempts
            
            return {
                'total_transactions_processed': total_transactions,
                'total_duplicate_attempts': total_duplicates,
                'unique_transactions_with_duplicates': unique_duplicated_transactions,
                'recent_duplicate_attempts': recent_duplicates,
                'bloom_filter_size': len(self.bloom_filter),
                'hash_table_size': len(self.transaction_hashes),
                'duplicate_rate': total_duplicates / max(total_transactions, 1),
                'top_duplicated_transactions': self._get_top_duplicated_transactions(5)
            }
    
    def _get_top_duplicated_transactions(self, limit: int = 5) -> List[Dict]:
        """Get transactions with the most duplicate attempts"""
        sorted_duplicates = sorted(
            self.duplicate_attempts.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        return [
            {
                'transaction_id': txn_id,
                'duplicate_attempts': attempts,
                'timestamp': self.transaction_timestamps.get(txn_id, 0)
            }
            for txn_id, attempts in sorted_duplicates[:limit]
        ]
    
    def _cleanup_loop(self):
        """Periodic cleanup of old deduplication records"""
        while self.is_running:
            try:
                self._cleanup_old_records()
                time.sleep(self.cleanup_interval)
            except Exception as e:
                self.logger.error(f"Error in cleanup loop: {e}")
                time.sleep(300)  # Wait 5 minutes on error
    
    def _cleanup_old_records(self):
        """Clean up old deduplication records to prevent memory bloat"""
        current_time = time.time()
        cutoff_time = current_time - self.retention_period
        
        with self.dedup_lock:
            # Find old transactions to clean up
            old_transactions = []
            for txn_id, timestamp in self.transaction_timestamps.items():
                if timestamp < cutoff_time:
                    old_transactions.append(txn_id)
            
            # Clean up old records
            cleaned_count = 0
            for txn_id in old_transactions:
                # Remove from all tracking structures
                if txn_id in self.transaction_hashes:
                    content_hash = self.transaction_hashes[txn_id]
                    
                    # Remove from hash_to_transactions
                    if content_hash in self.hash_to_transactions:
                        self.hash_to_transactions[content_hash].remove(txn_id)
                        if not self.hash_to_transactions[content_hash]:
                            del self.hash_to_transactions[content_hash]
                            # Also remove from bloom filter
                            self.bloom_filter.discard(content_hash)
                    
                    del self.transaction_hashes[txn_id]
                
                self.processed_transactions.discard(txn_id)
                self.duplicate_attempts.pop(txn_id, None)
                del self.transaction_timestamps[txn_id]
                
                cleaned_count += 1
            
            if cleaned_count > 0:
                self.logger.info(f"Cleaned up {cleaned_count} old deduplication records")
    
    def force_cleanup(self):
        """Force immediate cleanup of old records"""
        self.logger.info("Forcing immediate cleanup of deduplication records")
        self._cleanup_old_records()
    
    def reset_deduplication_data(self):
        """Reset all deduplication data (use with caution!)"""
        with self.dedup_lock:
            self.transaction_hashes.clear()
            self.hash_to_transactions.clear()
            self.processed_transactions.clear()
            self.duplicate_attempts.clear()
            self.transaction_timestamps.clear()
            self.bloom_filter.clear()
            
            self.logger.warning("All deduplication data has been reset")
    
    def export_deduplication_report(self) -> Dict:
        """Export comprehensive deduplication report for analysis"""
        with self.dedup_lock:
            current_time = time.time()
            
            # Analyze duplicate patterns
            duplicate_patterns = {}
            for txn_id, attempts in self.duplicate_attempts.items():
                if attempts > 1:
                    txn_time = self.transaction_timestamps.get(txn_id, 0)
                    age_hours = (current_time - txn_time) / 3600
                    
                    pattern_key = f"{attempts}_attempts"
                    if pattern_key not in duplicate_patterns:
                        duplicate_patterns[pattern_key] = []
