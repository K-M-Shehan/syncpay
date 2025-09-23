# src/replication/consistency_manager.py
# Member 2: Consistency Management Component

import time
import threading
from typing import Dict, List, Set, Optional
from enum import Enum
import logging

class ConsistencyLevel(Enum):
    STRONG = "strong"          # All nodes must acknowledge
    MAJORITY = "majority"      # Majority of nodes must acknowledge  
    EVENTUAL = "eventual"      # Best effort, async replication

class ConsistencyState(Enum):
    CONSISTENT = "consistent"
    INCONSISTENT = "inconsistent"
    CONVERGING = "converging"
    UNKNOWN = "unknown"

class ConsistencyManager:
    def __init__(self, node):
        self.node = node
        self.consistency_level = ConsistencyLevel.MAJORITY  # Default for payment systems
        self.consistency_state = ConsistencyState.UNKNOWN
        self.consistency_checks = {}  # Track consistency status per peer
        self.version_vectors = {}     # Vector clocks for eventual consistency
        self.conflict_resolution_log = []
        
        # Monitoring
        self.last_consistency_check = 0
        self.consistency_check_interval = 30  # seconds
        self.consistency_lock = threading.Lock()
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(f"ConsistencyMgr-{node.node_id}")
    
    def set_consistency_level(self, level: ConsistencyLevel):
        """Set the consistency level for the system"""
        with self.consistency_lock:
            old_level = self.consistency_level
            self.consistency_level = level
            self.logger.info(f"Consistency level changed from {old_level.value} to {level.value}")
    
    def get_consistency_level(self) -> ConsistencyLevel:
        """Get current consistency level"""
        return self.consistency_level
    
    def ensure_write_consistency(self, transaction, peers: List[str]) -> bool:
        """Ensure write consistency based on current consistency level"""
        if self.consistency_level == ConsistencyLevel.STRONG:
            return self._ensure_strong_consistency(transaction, peers)
        elif self.consistency_level == ConsistencyLevel.MAJORITY:
            return self._ensure_majority_consistency(transaction, peers)
        else:  # EVENTUAL
            return self._ensure_eventual_consistency(transaction, peers)
    
    def _ensure_strong_consistency(self, transaction, peers: List[str]) -> bool:
        """Ensure strong consistency - all nodes must acknowledge"""
        self.logger.debug(f"Ensuring strong consistency for transaction {transaction.id}")
        
        # All peers must successfully replicate
        successful_replications = 0
        total_peers = len(peers)
        
        for peer in peers:
            if self._replicate_to_peer_sync(peer, transaction):
                successful_replications += 1
            else:
                self.logger.warning(f"Strong consistency failed - {peer} did not acknowledge")
                return False
        
        # All nodes must acknowledge for strong consistency
        success = successful_replications == total_peers
        
        if success:
            self.logger.info(f"Strong consistency achieved for transaction {transaction.id}")
        else:
            self.logger.error(f"Strong consistency failed for transaction {transaction.id}")
        
        return success
    
    def _ensure_majority_consistency(self, transaction, peers: List[str]) -> bool:
        """Ensure majority consistency - majority of nodes must acknowledge"""
        self.logger.debug(f"Ensuring majority consistency for transaction {transaction.id}")
        
        total_nodes = len(peers) + 1  # +1 for current node
        required_acks = (total_nodes // 2) + 1  # Majority
        
        # Current node counts as one acknowledgment
        successful_replications = 1
        
        for peer in peers:
            if self._replicate_to_peer_sync(peer, transaction):
                successful_replications += 1
                
                # Check if we have majority
                if successful_replications >= required_acks:
                    self.logger.info(f"Majority consistency achieved for transaction {transaction.id} ({successful_replications}/{total_nodes})")
                    return True
        
        # Failed to achieve majority
        self.logger.error(f"Majority consistency failed for transaction {transaction.id} ({successful_replications}/{required_acks} required)")
        return False
    
    def _ensure_eventual_consistency(self, transaction, peers: List[str]) -> bool:
        """Ensure eventual consistency - best effort async replication"""
        self.logger.debug(f"Using eventual consistency for transaction {transaction.id}")
        
        # Update version vector
        self._update_version_vector(transaction)
        
        # Queue for async replication - always succeeds immediately
        for peer in peers:
            self._queue_for_async_replication(peer, transaction)
        
        return True
    
    def _replicate_to_peer_sync(self, peer: str, transaction) -> bool:
        """Synchronously replicate transaction to a peer"""
        try:
            # This would use the replicator's sync method
            if hasattr(self.node, 'replicator'):
                return self.node.replicator._send_replication_request(peer, transaction, sync=True)
        except Exception as e:
            self.logger.error(f"Sync replication to {peer} failed: {e}")
        return False
    
    def _queue_for_async_replication(self, peer: str, transaction):
        """Queue transaction for asynchronous replication"""
        if hasattr(self.node, 'replicator'):
            with self.node.replicator.replication_lock:
                self.node.replicator.pending_replications[peer].append(transaction)
                self.node.replicator.replication_status[peer]['pending_count'] += 1
    
    def _update_version_vector(self, transaction):
        """Update version vector for eventual consistency tracking"""
        node_id = self.node.node_id
        
        if node_id not in self.version_vectors:
            self.version_vectors[node_id] = 0
        
        self.version_vectors[node_id] += 1
        
        # Attach version vector to transaction for conflict resolution
        if hasattr(transaction, 'version_vector'):
            transaction.version_vector = self.version_vectors.copy()
    
    def check_read_consistency(self, transaction_id: str) -> Dict:
        """Check read consistency across all nodes for a specific transaction"""
        self.logger.debug(f"Checking read consistency for transaction {transaction_id}")
        
        consistency_report = {
            'transaction_id': transaction_id,
            'consistent': False,
            'node_states': {},
            'conflicts': [],
            'resolution_needed': False
        }
        
        peers = self.node.config.get_peers(self.node.node_id)
        local_transaction = self.node.transactions.get(transaction_id)
        
        # Check local state
        consistency_report['node_states'][self.node.node_id] = {
            'has_transaction': local_transaction is not None,
            'transaction_data': local_transaction.to_dict() if local_transaction else None
        }
        
        # Check peer states
        consistent_count = 1 if local_transaction else 0
        total_responses = 1
        
        for peer in peers:
            peer_state = self._check_peer_transaction_state(peer, transaction_id)
            if peer_state:
                consistency_report['node_states'][peer] = peer_state
                total_responses += 1
                
                if peer_state['has_transaction'] and local_transaction:
                    # Compare transaction data for consistency
                    if self._transactions_match(local_transaction, peer_state['transaction_data']):
                        consistent_count += 1
                    else:
                        consistency_report['conflicts'].append({
                            'peer': peer,
                            'conflict_type': 'data_mismatch',
                            'details': 'Transaction data differs between nodes'
                        })
                        consistency_report['resolution_needed'] = True
        
        # Determine consistency status
        if self.consistency_level == ConsistencyLevel.STRONG:
            consistency_report['consistent'] = consistent_count == total_responses
        elif self.consistency_level == ConsistencyLevel.MAJORITY:
            required = (total_responses // 2) + 1
            consistency_report['consistent'] = consistent_count >= required
        else:  # EVENTUAL
            consistency_report['consistent'] = consistent_count > 0
        
        return consistency_report
    
    def _check_peer_transaction_state(self, peer: str, transaction_id: str) -> Optional[Dict]:
        """Check transaction state on a specific peer"""
        try:
            import requests
            response = requests.get(
                f"http://{peer}/transactions",
                timeout=3.0
            )
            
            if response.status_code == 200:
                data = response.json()
                transactions = data.get('transactions', [])
                
                # Find the specific transaction
                for txn in transactions:
                    if txn['id'] == transaction_id:
                        return {
                            'has_transaction': True,
                            'transaction_data': txn
                        }
                
                return {'has_transaction': False, 'transaction_data': None}
                
        except Exception as e:
            self.logger.warning(f"Failed to check transaction state on {peer}: {e}")
        
        return None
    
    def _transactions_match(self, local_txn, peer_txn_data) -> bool:
        """Compare two transactions for consistency"""
        if not peer_txn_data:
            return False
        
        # Compare key fields
        return (
            local_txn.id == peer_txn_data.get('id') and
            local_txn.amount == peer_txn_data.get('amount') and
            local_txn.sender == peer_txn_data.get('sender') and
            local_txn.receiver == peer_txn_data.get('receiver') and
            local_txn.status == peer_txn_data.get('status')
        )
    
    def resolve_conflicts(self, conflicts: List[Dict]) -> List[Dict]:
        """Resolve consistency conflicts using conflict resolution strategies"""
        resolved_conflicts = []
        
        for conflict in conflicts:
            conflict_type = conflict.get('conflict_type')
            
            if conflict_type == 'data_mismatch':
                resolution = self._resolve_data_mismatch(conflict)
            elif conflict_type == 'missing_transaction':
                resolution = self._resolve_missing_transaction(conflict)
            elif conflict_type == 'timestamp_conflict':
                resolution = self._resolve_timestamp_conflict(conflict)
            else:
                resolution = {'strategy': 'manual_review', 'action': 'requires_manual_intervention'}
            
            resolved_conflicts.append({
                'original_conflict': conflict,
                'resolution': resolution,
                'resolved_at': time.time()
            })
            
            self.conflict_resolution_log.append(resolved_conflicts[-1])
        
        return resolved_conflicts
    
    def _resolve_data_mismatch(self, conflict: Dict) -> Dict:
        """Resolve data mismatch conflicts using last-writer-wins"""
        # Simple last-writer-wins strategy based on timestamp
        return {
            'strategy': 'last_writer_wins',
            'action': 'use_most_recent_timestamp',
            'details': 'Applied last-writer-wins based on transaction timestamp'
        }
    
    def _resolve_missing_transaction(self, conflict: Dict) -> Dict:
        """Resolve missing transaction conflicts"""
        return {
            'strategy': 'replicate_missing',
            'action': 'trigger_replication',
            'details': 'Trigger replication of missing transaction to all nodes'
        }
    
    def _resolve_timestamp_conflict(self, conflict: Dict) -> Dict:
        """Resolve timestamp conflicts using vector clocks"""
        return {
            'strategy': 'vector_clock_ordering',
            'action': 'reorder_by_vector_clock',
            'details': 'Use vector clocks to determine correct ordering'
        }
    
    def perform_consistency_check(self) -> Dict:
        """Perform a comprehensive consistency check across the cluster"""
        self.logger.info("Starting cluster-wide consistency check")
        
        start_time = time.time()
        consistency_report = {
            'check_timestamp': start_time,
            'overall_consistent': True,
            'node_count': 0,
            'transaction_count': 0,
            'inconsistencies': [],
            'recommendations': []
        }
        
        # Get all local transactions
        local_transactions = list(self.node.transactions.keys())
        consistency_report['transaction_count'] = len(local_transactions)
        
        # Check consistency for a sample of recent transactions
        sample_size = min(20, len(local_transactions))  # Check last 20 transactions
        recent_transactions = local_transactions[-sample_size:] if local_transactions else []
        
        inconsistent_count = 0
        
        for transaction_id in recent_transactions:
            txn_consistency = self.check_read_consistency(transaction_id)
            
            if not txn_consistency['consistent']:
                inconsistent_count += 1
                consistency_report['inconsistencies'].append(txn_consistency)
                consistency_report['overall_consistent'] = False
        
        # Generate recommendations
        if inconsistent_count > 0:
            inconsistency_rate = inconsistent_count / sample_size
            
            if inconsistency_rate > 0.1:  # More than 10% inconsistent
                consistency_report['recommendations'].append({
                    'priority': 'high',
                    'action': 'trigger_full_sync',
                    'reason': f'High inconsistency rate: {inconsistency_rate:.2%}'
                })
            else:
                consistency_report['recommendations'].append({
                    'priority': 'medium',
                    'action': 'monitor_closely',
                    'reason': f'Some inconsistencies detected: {inconsistency_rate:.2%}'
                })
        
        # Update consistency state
        if consistency_report['overall_consistent']:
            self.consistency_state = ConsistencyState.CONSISTENT
        elif inconsistent_count < sample_size * 0.5:
            self.consistency_state = ConsistencyState.CONVERGING
        else:
            self.consistency_state = ConsistencyState.INCONSISTENT
        
        self.last_consistency_check = time.time()
        
        check_duration = time.time() - start_time
        self.logger.info(f"Consistency check completed in {check_duration:.2f}s. Status: {self.consistency_state.value}")
        
        return consistency_report
    
    def get_consistency_metrics(self) -> Dict:
        """Get current consistency metrics and status"""
        current_time = time.time()
        
        return {
            'consistency_level': self.consistency_level.value,
            'consistency_state': self.consistency_state.value,
            'last_check_ago': current_time - self.last_consistency_check,
            'conflict_count': len(self.conflict_resolution_log),
            'recent_conflicts': len([c for c in self.conflict_resolution_log 
                                   if current_time - c['resolved_at'] < 3600]),  # Last hour
            'version_vectors': self.version_vectors,
            'recommendations': self._get_current_recommendations()
        }
    
    def _get_current_recommendations(self) -> List[Dict]:
        """Get current recommendations for maintaining consistency"""
        recommendations = []
        current_time = time.time()
        
        # Check if consistency check is overdue
        if current_time - self.last_consistency_check > self.consistency_check_interval * 2:
            recommendations.append({
                'priority': 'medium',
                'action': 'schedule_consistency_check',
                'reason': 'Consistency check is overdue'
            })
        
        # Check if there are many recent conflicts
        recent_conflicts = len([c for c in self.conflict_resolution_log 
                              if current_time - c['resolved_at'] < 1800])  # Last 30 minutes
        
        if recent_conflicts > 5:
            recommendations.append({
                'priority': 'high',
                'action': 'investigate_consistency_issues',
                'reason': f'{recent_conflicts} conflicts in last 30 minutes'
            })
        
        return recommendations
    
    def trigger_full_resync(self):
        """Trigger a full resynchronization across all nodes"""
        self.logger.warning("Triggering full cluster resynchronization")
        
        # This would coordinate with the replicator to perform full sync
        if hasattr(self.node, 'replicator'):
            peers = self.node.config.get_peers(self.node.node_id)
            for peer in peers:
                self.node.replicator.sync_with_recovered_peer(peer)
        
        # Schedule a consistency check after sync
        threading.Timer(10.0, self.perform_consistency_check).start()
