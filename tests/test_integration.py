# tests/test_integration.py
# Integration tests for SyncPay distributed payment system

import unittest
import time
import threading
import requests
import json
from unittest.mock import patch
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from main import SyncPayNode
from models import PaymentTransaction

class TestSyncPayIntegration(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        """Set up test class - start test nodes"""
        cls.nodes = {}
        cls.node_ports = {'node1': 5100, 'node2': 5101, 'node3': 5102}
        
        # Mock config to use test ports
        with patch('config.Config') as MockConfig:
            mock_config = MockConfig.return_value
            mock_config.node_configs = {
                'node1': {'host': 'localhost', 'port': 5100},
                'node2': {'host': 'localhost', 'port': 5101},
                'node3': {'host': 'localhost', 'port': 5102}
            }
            mock_config.get_peers.side_effect = lambda node_id: [
                f"localhost:{port}" for nid, port in cls.node_ports.items() 
                if nid != node_id
            ]
            
            # Create test nodes (don't start Flask servers)
            for node_id in ['node1', 'node2', 'node3']:
                cls.nodes[node_id] = SyncPayNode(node_id)
    
    def setUp(self):
        """Set up each test"""
        # Reset node states
        for node in self.nodes.values():
            node.transactions.clear()
            node.transaction_log.clear()
            node.consensus.state = node.consensus.state.__class__.FOLLOWER
            # Reset deduplication manager
            node.deduplication_manager.transaction_hashes.clear()
            node.deduplication_manager.hash_to_transactions.clear()
            node.deduplication_manager.processed_transactions.clear()
            node.deduplication_manager.duplicate_attempts.clear()
            node.consensus.current_term = 0
            node.consensus.log.clear()
    
    def test_transaction_creation(self):
        """Test basic transaction creation"""
        node = self.nodes['node1']
        
        transaction = PaymentTransaction.create(
            amount=100.0,
            sender='alice',
            receiver='bob',
            node_id='node1'
        )
        
        self.assertIsNotNone(transaction.id)
        self.assertEqual(transaction.amount, 100.0)
        self.assertEqual(transaction.sender, 'alice')
        self.assertEqual(transaction.receiver, 'bob')
        self.assertEqual(transaction.status, 'pending')
    
    def test_deduplication_integration(self):
        """Test deduplication across components"""
        node = self.nodes['node1']
        
        # Create identical transactions
        transaction1 = PaymentTransaction.create(100.0, 'alice', 'bob', 'node1')
        transaction2 = PaymentTransaction.create(100.0, 'alice', 'bob', 'node1')
        
        # Register first transaction
        node.deduplication_manager.register_transaction(transaction1)
        
        # Check second transaction for duplicate
        is_duplicate, original_id = node.deduplication_manager.is_duplicate_transaction(transaction2)
        
        # Should detect duplicate content
        self.assertTrue(is_duplicate)
        self.assertEqual(original_id, transaction1.id)
    
    def test_replication_deduplication_flow(self):
        """Test replication with deduplication"""
        replicator = self.nodes['node1'].replicator
        
        # Create test request data
        transaction_data = {
            'id': 'test-txn-123',
            'amount': 100.0,
            'sender': 'alice',
            'receiver': 'bob',
            'timestamp': time.time(),
            'status': 'confirmed',
            'node_id': 'source_node'
        }
        
        # Mock Flask request
        from unittest.mock import Mock
        mock_request = Mock()
        mock_request.get_json.return_value = {
            'transaction': transaction_data,
            'source_node': 'source_node'
        }
        
        # First replication should succeed
        response1, status1 = replicator.handle_replication_request(mock_request)
        self.assertEqual(status1, 200)
        self.assertEqual(response1['status'], 'success')
        
        # Second replication should detect duplicate
        response2, status2 = replicator.handle_replication_request(mock_request)
        self.assertEqual(status2, 200)
        self.assertEqual(response2['status'], 'duplicate')
    
    def test_consensus_transaction_flow(self):
        """Test consensus integration with transactions"""
        node = self.nodes['node1']
        consensus = node.consensus
        
        # Make node1 the leader
        consensus.state = consensus.state.__class__.LEADER
        consensus.current_term = 1
        
        # Create transaction
        transaction = PaymentTransaction.create(100.0, 'alice', 'bob', 'node1')
        
        # Mock successful replication
        with patch.object(consensus, '_replicate_to_majority', return_value=True):
            result = consensus.propose_transaction(transaction)
            
            self.assertTrue(result)
            self.assertEqual(len(consensus.log), 1)
            self.assertEqual(consensus.log[0], (1, transaction.id))
    
    def test_time_sync_accuracy(self):
        """Test time synchronization accuracy"""
        node = self.nodes['node1']
        time_sync = node.time_sync
        
        # Test basic time functions
        sync_time1 = time_sync.get_synchronized_time()
        system_time = time.time()
        
        # Should be close to system time initially (no offset)
        self.assertAlmostEqual(sync_time1, system_time, delta=0.1)
        
        # Set an offset and test
        time_sync.time_offset = 0.5
        sync_time2 = time_sync.get_synchronized_time()
        
        self.assertAlmostEqual(sync_time2, system_time + 0.5, delta=0.1)
    
    def test_health_monitoring_integration(self):
        """Test health monitoring with other components"""
        node = self.nodes['node1']
        health_monitor = node.health_monitor
        
        # Initialize peer status
        health_monitor.peer_status = {
            'localhost:5101': {
                'is_healthy': True,
                'consecutive_failures': 0,
                'last_check': time.time(),
                'last_successful_check': time.time(),
                'response_time': 0.1
            }
        }
        
        # Test getting healthy peers
        healthy_peers = health_monitor.get_healthy_peers()
        self.assertIn('localhost:5101', healthy_peers)
        
        # Test cluster health
        self.assertTrue(health_monitor.is_cluster_healthy())
    
    def test_component_lifecycle(self):
        """Test starting and stopping all components"""
        node = self.nodes['node1']
        
        # Components should not be running initially
        self.assertFalse(node.health_monitor.is_running)
        self.assertFalse(node.replicator.is_running)
        self.assertFalse(node.time_sync.is_running)
        self.assertFalse(node.consensus.is_running)
        
        # Mock threading to avoid actual thread creation
        with patch('threading.Thread'):
            # Start all components
            node.health_monitor.start()
            node.replicator.start()
            node.time_sync.start()
            node.consensus.start()
            node.deduplication_manager.start()
            
            # Components should be running
            self.assertTrue(node.health_monitor.is_running)
            self.assertTrue(node.replicator.is_running)
            self.assertTrue(node.time_sync.is_running)
            self.assertTrue(node.consensus.is_running)
        
        # Stop all components
        node.health_monitor.stop()
        node.replicator.stop()
        node.time_sync.stop()
        node.consensus.stop()
        node.deduplication_manager.stop()
        
        # Components should be stopped
        self.assertFalse(node.health_monitor.is_running)
        self.assertFalse(node.replicator.is_running)
        self.assertFalse(node.time_sync.is_running)
        self.assertFalse(node.consensus.is_running)
    
    def test_batch_replication(self):
        """Test batch replication functionality"""
        replicator = self.nodes['node1'].replicator
        
        # Create batch transaction data
        transactions_data = [
            {
                'id': f'txn-{i}',
                'amount': 100.0 + i,
                'sender': 'alice',
                'receiver': 'bob',
                'timestamp': time.time(),
                'status': 'confirmed',
                'node_id': 'source_node'
            }
            for i in range(5)
        ]
        
        # Mock Flask request
        from unittest.mock import Mock
        mock_request = Mock()
        mock_request.get_json.return_value = {
            'transactions': transactions_data,
            'source_node': 'source_node',
            'is_sync': True
        }
        
        # Handle batch replication
        response, status_code = replicator.handle_batch_replication_request(mock_request)
        
        self.assertEqual(status_code, 200)
        self.assertEqual(response['status'], 'completed')
        self.assertEqual(response['successful_count'], 5)
        self.assertEqual(response['total_count'], 5)
        
        # Check all transactions were stored
        for i in range(5):
            self.assertIn(f'txn-{i}', self.nodes['node1'].transactions)
    
    def test_peer_failure_recovery_flow(self):
        """Test peer failure and recovery handling"""
        node = self.nodes['node1']
        failed_peer = 'localhost:5101'
        
        # Simulate peer failure
        node.health_monitor.handle_peer_failure(failed_peer)
        node.replicator.handle_peer_failure(failed_peer)
        node.consensus.handle_peer_failure(failed_peer)
        
        # Check failure was handled
        if failed_peer in node.replicator.replication_status:
            self.assertFalse(node.replicator.replication_status[failed_peer]['is_connected'])
        
        # Simulate peer recovery
        node.health_monitor.handle_peer_recovery(failed_peer)
        node.replicator.handle_peer_recovery(failed_peer)
        node.consensus.handle_peer_recovery(failed_peer)
        
        # Check recovery was handled
        if failed_peer in node.replicator.replication_status:
            self.assertTrue(node.replicator.replication_status[failed_peer]['is_connected'])
    
    def test_transaction_flow_end_to_end(self):
        """Test complete transaction flow"""
        node = self.nodes['node1']
        
        # Make node1 the leader
        node.consensus.state = node.consensus.state.__class__.LEADER
        node.consensus.current_term = 1
        
        # Create and process transaction
        transaction = PaymentTransaction.create(100.0, 'alice', 'bob', 'node1')
        
        # Apply time synchronization
        transaction.timestamp = node.time_sync.get_synchronized_time()
        
        # Mock consensus success
        with patch.object(node.consensus, '_replicate_to_majority', return_value=True):
            consensus_result = node.consensus.propose_transaction(transaction)
            self.assertTrue(consensus_result)
        
        # Store transaction
        node.transactions[transaction.id] = transaction
        node.transaction_log.append(transaction)
        
        # Register with deduplication
        node.deduplication_manager.register_transaction(transaction)
        
        # Mock replication to other nodes
        node.replicator.replicate_transaction(transaction)
        
        # Verify transaction is stored and tracked
        self.assertIn(transaction.id, node.transactions)
        self.assertIn(transaction, node.transaction_log)
        
        # Verify consensus log
        self.assertEqual(len(node.consensus.log), 1)
        self.assertEqual(node.consensus.log[0], (1, transaction.id))

if __name__ == '__main__':
    unittest.main()