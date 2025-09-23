# tests/test_time_synchronizer.py
# Unit tests for TimeSynchronizer component

import unittest
import time
import statistics
from unittest.mock import Mock, patch
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from time_sync.time_synchronizer import TimeSynchronizer
from config import Config

class TestTimeSynchronizer(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures"""
        # Create mock node
        self.mock_node = Mock()
        self.mock_node.node_id = 'test_node'
        self.mock_node.config = Config()
        
        # Create synchronizer instance
        self.sync = TimeSynchronizer(self.mock_node)
    
    def test_initialization(self):
        """Test TimeSynchronizer initialization"""
        self.assertEqual(self.sync.node, self.mock_node)
        self.assertEqual(self.sync.time_offset, 0.0)
        self.assertEqual(self.sync.clock_skew, 0.0)
        self.assertEqual(self.sync.sync_interval, 30.0)
        self.assertFalse(self.sync.is_running)
    
    def test_get_synchronized_time(self):
        """Test getting synchronized time"""
        # Set a test offset
        self.sync.time_offset = 1.5
        
        sync_time = self.sync.get_synchronized_time()
        expected_time = time.time() + 1.5
        
        # Should be within 0.1 seconds (accounting for execution time)
        self.assertAlmostEqual(sync_time, expected_time, delta=0.1)
    
    def test_get_time_offset(self):
        """Test getting time offset in milliseconds"""
        # Set test offset (in seconds)
        self.sync.time_offset = 0.123
        
        offset_ms = self.sync.get_time_offset()
        
        self.assertEqual(offset_ms, 123.0)  # 0.123 * 1000
    
    def test_get_sync_status(self):
        """Test getting synchronization status"""
        # Set some test values
        self.sync.time_offset = 0.001
        self.sync.clock_skew = 0.00001
        self.sync.sync_accuracy = 0.0005
        self.sync.last_sync_time = time.time() - 10
        self.sync.time_samples = [(0.001, time.time(), 0.01)]
        self.sync.peer_offsets = {'peer1:5001': [0.001, 0.002]}
        
        status = self.sync.get_sync_status()
        
        self.assertIn('time_offset_ms', status)
        self.assertIn('clock_skew_ppm', status)
        self.assertIn('sync_accuracy_ms', status)
        self.assertIn('sample_count', status)
        self.assertIn('peer_count', status)
        self.assertEqual(status['sample_count'], 1)
        self.assertEqual(status['peer_count'], 1)
    
    @patch('threading.Thread')
    def test_start_service(self, mock_thread):
        """Test starting the synchronization service"""
        with patch.object(self.sync, '_perform_initial_sync'):
            self.sync.start()
            
            self.assertTrue(self.sync.is_running)
            mock_thread.assert_called_once()
    
    def test_stop_service(self):
        """Test stopping the synchronization service"""
        # Mock sync thread
        mock_thread = Mock()
        self.sync.sync_thread = mock_thread
        self.sync.is_running = True
        
        self.sync.stop()
        
        self.assertFalse(self.sync.is_running)
        mock_thread.join.assert_called_with(timeout=5.0)
    
    @patch('requests.post')
    def test_sync_with_peer_success(self, mock_post):
        """Test successful synchronization with a peer"""
        # Mock successful response
        current_time = time.time()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            't2': current_time + 0.1,  # Peer received 0.1s later
            't3': current_time + 0.1   # Peer responded immediately
        }
        mock_post.return_value = mock_response
        
        # Sync with peer
        offset = self.sync._sync_with_peer('peer1:5001')
        
        self.assertIsNotNone(offset)
        self.assertIsInstance(offset, float)
        mock_post.assert_called()
    
    @patch('requests.post')
    def test_sync_with_peer_failure(self, mock_post):
        """Test failed synchronization with a peer"""
        # Mock failed response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response
        
        # Sync with peer
        offset = self.sync._sync_with_peer('peer1:5001')
        
        self.assertIsNone(offset)
    
    def test_filter_outliers(self):
        """Test outlier filtering"""
        # Test data with outliers
        offsets = [0.001, 0.002, 0.001, 0.002, 0.1, 0.001]  # 0.1 is outlier
        
        filtered = self.sync._filter_outliers(offsets)
        
        # Should remove the outlier
        self.assertNotIn(0.1, filtered)
        self.assertIn(0.001, filtered)
        self.assertIn(0.002, filtered)
    
    def test_filter_outliers_insufficient_data(self):
        """Test outlier filtering with insufficient data"""
        offsets = [0.001, 0.002]  # Less than 3 samples
        
        filtered = self.sync._filter_outliers(offsets)
        
        # Should return all data when insufficient samples
        self.assertEqual(filtered, offsets)
    
    def test_calculate_offset(self):
        """Test offset calculation"""
        # Add some sample data
        current_time = time.time()
        self.sync.time_samples = [
            (0.001, current_time - 10, 0.01),
            (0.002, current_time - 5, 0.01),
            (0.001, current_time, 0.01)
        ]
        
        old_offset = self.sync.time_offset
        self.sync._calculate_offset()
        
        # Offset should be updated
        self.assertNotEqual(self.sync.time_offset, old_offset)
    
    def test_has_enough_samples(self):
        """Test checking for sufficient samples"""
        # No samples
        self.assertFalse(self.sync._has_enough_samples())
        
        # Add samples for multiple peers
        self.sync.peer_offsets = {
            'peer1:5001': [0.001, 0.002],
            'peer2:5002': [0.002, 0.001]
        }
        
        # Should have enough samples (4 total >= 3 minimum)
        self.assertTrue(self.sync._has_enough_samples())
    
    def test_handle_sync_request(self):
        """Test handling incoming sync requests"""
        # Mock Flask request
        current_time = time.time()
        mock_request = Mock()
        mock_request.get_json.return_value = {
            't1': current_time - 0.1,
            'node_id': 'requesting_node'
        }
        
        # Handle request
        response, status_code = self.sync.handle_sync_request(mock_request)
        
        self.assertEqual(status_code, 200)
        self.assertIn('t2', response)
        self.assertIn('t3', response)
        self.assertIn('server_time', response)
        self.assertIn('offset_ms', response)
    
    def test_handle_sync_request_invalid(self):
        """Test handling invalid sync request"""
        # Mock invalid request
        mock_request = Mock()
        mock_request.get_json.return_value = {}  # Missing t1
        
        # Handle request
        response, status_code = self.sync.handle_sync_request(mock_request)
        
        self.assertEqual(status_code, 400)
        self.assertIn('error', response)
    
    def test_force_sync(self):
        """Test forcing immediate synchronization"""
        with patch.object(self.sync, '_perform_sync_round') as mock_sync:
            self.sync.force_sync()
            mock_sync.assert_called_once()
    
    def test_reset_sync(self):
        """Test resetting synchronization state"""
        # Set some state
        self.sync.time_offset = 1.0
        self.sync.clock_skew = 0.1
        self.sync.sync_accuracy = 0.05
        self.sync.time_samples = [(0.1, time.time(), 0.01)]
        self.sync.peer_offsets = {'peer1': [0.1]}
        
        # Reset
        self.sync.reset_sync()
        
        # Check everything is reset
        self.assertEqual(self.sync.time_offset, 0.0)
        self.assertEqual(self.sync.clock_skew, 0.0)
        self.assertEqual(self.sync.sync_accuracy, 0.0)
        self.assertEqual(len(self.sync.time_samples), 0)
        self.assertEqual(len(self.sync.peer_offsets), 0)

if __name__ == '__main__':
    unittest.main()