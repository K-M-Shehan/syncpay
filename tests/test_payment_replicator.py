# tests/test_payment_replicator.py
# Unit tests for PaymentReplicator component

import unittest
import time
import threading
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from replication.replicator import PaymentReplicator
from models import PaymentTransaction
from config import Config

class TestPaymentReplicator(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures"""
        # Create mock node
        self.mock_node = Mock()
        self.mock_node.node_id = 'test_node'
        self.mock_node.config = Config()
        self.mock_node.transactions = {}
        self.mock_node.transaction_log = []
        self.mock_node._transaction_lock = threading.Lock()
        
        # Mock deduplication manager
        self.mock_dedup = Mock()
        self.mock_dedup.is_duplicate_transaction.return_value = (False, None)
        self.mock_node.deduplication_manager = self.mock_dedup
        
        # Create replicator instance
        self.replicator = PaymentReplicator(self.mock_node)
    
    def test_initialization(self):
        """Test PaymentReplicator initialization"""
        self.assertEqual(self.replicator.node, self.mock_node)
        self.assertIsInstance(self.replicator.replication_status, dict)
        self.assertIsInstance(self.replicator.pending_replications, dict)
        self.assertEqual(self.replicator.num_workers, 3)
        self.assertFalse(self.replicator.is_running)
    
    def test_start_service(self):
        """Test starting the replication service"""
        with patch('threading.Thread') as mock_thread:
            self.replicator.start()
            
            self.assertTrue(self.replicator.is_running)
            # Should create worker threads
            self.assertEqual(mock_thread.call_count, self.replicator.num_workers)
    
    def test_stop_service(self):
        """Test stopping the replication service"""
        # Start first
        self.replicator.start()
        
        # Mock worker threads
        mock_worker = Mock()
        self.replicator.worker_threads = [mock_worker]
        
        # Stop
        self.replicator.stop()
        
        self.assertFalse(self.replicator.is_running)
        mock_worker.join.assert_called_with(timeout=5.0)
    
    def test_replicate_transaction(self):
        """Test transaction replication queuing"""
        # Create test transaction
        transaction = PaymentTransaction.create(
            amount=100.0,
            sender='alice',
            receiver='bob',
            node_id='test_node'
        )
        
        # Mock peers
        with patch.object(self.mock_node.config, 'get_peers', return_value=['peer1:5001', 'peer2:5002']):
            self.replicator.start()
            
            # Replicate transaction
            self.replicator.replicate_transaction(transaction)
            
            # Check that transaction was queued for both peers
            self.assertEqual(len(self.replicator.pending_replications['peer1:5001']), 1)
            self.assertEqual(len(self.replicator.pending_replications['peer2:5002']), 1)
            
            # Check metrics
            self.assertEqual(self.replicator.replication_stats['total_sent'], 2)
    
    def test_send_replication_request_success(self):
        """Test successful replication request"""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'status': 'success'}
        
        # Mock the session.post method
        with patch.object(self.replicator.session, 'post', return_value=mock_response) as mock_post:
            # Create test transaction
            transaction = PaymentTransaction.create(
                amount=100.0,
                sender='alice',
                receiver='bob',
                node_id='test_node'
            )
            
            # Test replication
            result = self.replicator._send_replication_request('peer1:5001', transaction)
            
            self.assertTrue(result)
            mock_post.assert_called_once()
    
    def test_send_replication_request_failure(self):
        """Test failed replication request"""
        # Mock failed response
        mock_response = Mock()
        mock_response.status_code = 500
        
        # Mock the session.post method
        with patch.object(self.replicator.session, 'post', return_value=mock_response) as mock_post:
            # Create test transaction
            transaction = PaymentTransaction.create(
                amount=100.0,
                sender='alice',
                receiver='bob',
                node_id='test_node'
            )
            
            # Test replication
            result = self.replicator._send_replication_request('peer1:5001', transaction)
            
            self.assertFalse(result)
    
    def test_handle_replication_request_success(self):
        """Test handling incoming replication request"""
        # Mock Flask request
        mock_request = Mock()
        mock_request.get_json.return_value = {
            'transaction': {
                'id': 'test-txn-123',
                'amount': 100.0,
                'sender': 'alice',
                'receiver': 'bob',
                'timestamp': time.time(),
                'status': 'confirmed',
                'node_id': 'source_node'
            },
            'source_node': 'source_node',
            'timestamp': time.time()
        }
        
        # Handle request
        response, status_code = self.replicator.handle_replication_request(mock_request)
        
        self.assertEqual(status_code, 200)
        self.assertEqual(response['status'], 'success')
        self.assertIn('test-txn-123', self.mock_node.transactions)
    
    def test_handle_replication_request_duplicate(self):
        """Test handling duplicate transaction"""
        # Mock deduplication to return duplicate
        self.mock_dedup.is_duplicate_transaction.return_value = (True, 'original-txn-123')
        
        # Mock Flask request
        mock_request = Mock()
        mock_request.get_json.return_value = {
            'transaction': {
                'id': 'test-txn-123',
                'amount': 100.0,
                'sender': 'alice',
                'receiver': 'bob',
                'timestamp': time.time(),
                'status': 'confirmed',
                'node_id': 'source_node'
            },
            'source_node': 'source_node'
        }
        
        # Handle request
        response, status_code = self.replicator.handle_replication_request(mock_request)
        
        self.assertEqual(status_code, 200)
        self.assertEqual(response['status'], 'duplicate')
        self.assertEqual(response['original_transaction_id'], 'original-txn-123')
    
    def test_handle_batch_replication_request(self):
        """Test handling batch replication request"""
        # Mock Flask request with batch
        mock_request = Mock()
        mock_request.get_json.return_value = {
            'transactions': [
                {
                    'id': 'txn-1',
                    'amount': 100.0,
                    'sender': 'alice',
                    'receiver': 'bob',
                    'timestamp': time.time(),
                    'status': 'confirmed',
                    'node_id': 'source_node'
                },
                {
                    'id': 'txn-2',
                    'amount': 200.0,
                    'sender': 'bob',
                    'receiver': 'charlie',
                    'timestamp': time.time(),
                    'status': 'confirmed',
                    'node_id': 'source_node'
                }
            ],
            'source_node': 'source_node',
            'is_sync': True
        }
        
        # Handle batch request
        response, status_code = self.replicator.handle_batch_replication_request(mock_request)
        
        self.assertEqual(status_code, 200)
        self.assertEqual(response['status'], 'completed')
        self.assertEqual(response['successful_count'], 2)
        self.assertEqual(response['total_count'], 2)
        
        # Check transactions were stored
        self.assertIn('txn-1', self.mock_node.transactions)
        self.assertIn('txn-2', self.mock_node.transactions)
    
    def test_get_replication_status(self):
        """Test getting replication status"""
        # Initialize some status data
        self.replicator.start()
        
        status = self.replicator.get_replication_status()
        
        self.assertIsInstance(status, dict)
        # Should have status for peers from config
        peers = self.mock_node.config.get_peers(self.mock_node.node_id)
        for peer in peers:
            self.assertIn(peer, status)
            self.assertIn('connected', status[peer])
            self.assertIn('pending_count', status[peer])
    
    def test_peer_failure_handling(self):
        """Test handling peer failure"""
        self.replicator.start()
        
        # Add some pending replications
        transaction = PaymentTransaction.create(100.0, 'alice', 'bob', 'test_node')
        self.replicator.pending_replications['peer1:5001'].append(transaction)
        self.replicator.replication_status['peer1:5001'] = {
            'is_connected': True,
            'pending_count': 1
        }
        
        # Handle failure
        self.replicator.handle_peer_failure('peer1:5001')
        
        # Check that peer is marked as disconnected and queue is cleared
        self.assertFalse(self.replicator.replication_status['peer1:5001']['is_connected'])
        self.assertEqual(len(self.replicator.pending_replications['peer1:5001']), 0)
    
    def test_peer_recovery_handling(self):
        """Test handling peer recovery"""
        self.replicator.start()
        
        # Mark peer as failed
        self.replicator.replication_status['peer1:5001'] = {
            'is_connected': False,
            'consecutive_failures': 5
        }
        
        # Handle recovery
        self.replicator.handle_peer_recovery('peer1:5001')
        
        # Check that peer is marked as connected
        self.assertTrue(self.replicator.replication_status['peer1:5001']['is_connected'])
        self.assertEqual(self.replicator.replication_status['peer1:5001']['consecutive_failures'], 0)

if __name__ == '__main__':
    unittest.main()