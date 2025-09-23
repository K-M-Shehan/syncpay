# tests/test_raft_consensus.py
# Unit tests for RaftConsensus component

import unittest
import time
from unittest.mock import Mock, patch
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from consensus.raft_consensus import RaftConsensus, RaftState
from models import PaymentTransaction
from config import Config

class TestRaftConsensus(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures"""
        # Create mock node
        self.mock_node = Mock()
        self.mock_node.node_id = 'test_node'
        self.mock_node.config = Config()
        
        # Create consensus instance
        self.raft = RaftConsensus(self.mock_node)
    
    def test_initialization(self):
        """Test RaftConsensus initialization"""
        self.assertEqual(self.raft.node, self.mock_node)
        self.assertEqual(self.raft.state, RaftState.FOLLOWER)
        self.assertEqual(self.raft.current_term, 0)
        self.assertIsNone(self.raft.voted_for)
        self.assertIsNone(self.raft.current_leader)
        self.assertEqual(len(self.raft.log), 0)
        self.assertFalse(self.raft.is_running)
    
    def test_is_leader(self):
        """Test leadership status checking"""
        # Initially not leader
        self.assertFalse(self.raft.is_leader())
        
        # Become leader
        self.raft.state = RaftState.LEADER
        self.assertTrue(self.raft.is_leader())
        
        # Back to follower
        self.raft.state = RaftState.FOLLOWER
        self.assertFalse(self.raft.is_leader())
    
    @patch('threading.Thread')
    def test_start_service(self, mock_thread):
        """Test starting the consensus service"""
        self.raft.start()
        
        self.assertTrue(self.raft.is_running)
        mock_thread.assert_called_once()
        
        # Check peer tracking initialization
        peers = self.mock_node.config.get_peers(self.mock_node.node_id)
        for peer in peers:
            self.assertIn(peer, self.raft.next_index)
            self.assertIn(peer, self.raft.match_index)
    
    def test_stop_service(self):
        """Test stopping the consensus service"""
        # Mock consensus thread
        mock_thread = Mock()
        self.raft.consensus_thread = mock_thread
        self.raft.is_running = True
        
        self.raft.stop()
        
        self.assertFalse(self.raft.is_running)
        mock_thread.join.assert_called_with(timeout=5.0)
    
    def test_propose_transaction_not_leader(self):
        """Test proposing transaction when not leader"""
        transaction = PaymentTransaction.create(100.0, 'alice', 'bob', 'test_node')
        
        # Should fail when not leader
        result = self.raft.propose_transaction(transaction)
        self.assertFalse(result)
    
    def test_propose_transaction_as_leader(self):
        """Test proposing transaction as leader"""
        # Become leader
        self.raft.state = RaftState.LEADER
        self.raft.current_term = 1
        
        transaction = PaymentTransaction.create(100.0, 'alice', 'bob', 'test_node')
        
        with patch.object(self.raft, '_replicate_to_majority', return_value=True):
            result = self.raft.propose_transaction(transaction)
            
            self.assertTrue(result)
            # Check log entry was added
            self.assertEqual(len(self.raft.log), 1)
            self.assertEqual(self.raft.log[0], (1, transaction.id))
    
    def test_start_election(self):
        """Test starting an election"""
        old_term = self.raft.current_term
        
        with patch.object(self.raft, '_request_vote'):
            self.raft._start_election()
            
            # Should become candidate
            self.assertEqual(self.raft.state, RaftState.CANDIDATE)
            # Should increment term
            self.assertEqual(self.raft.current_term, old_term + 1)
            # Should vote for self
            self.assertEqual(self.raft.voted_for, self.mock_node.node_id)
            self.assertIn(self.mock_node.node_id, self.raft.votes_received)
    
    def test_become_leader(self):
        """Test becoming leader"""
        # Set up as candidate
        self.raft.state = RaftState.CANDIDATE
        self.raft.current_term = 5
        
        self.raft._become_leader()
        
        # Should become leader
        self.assertEqual(self.raft.state, RaftState.LEADER)
        self.assertEqual(self.raft.current_leader, self.mock_node.node_id)
        
        # Should initialize leader state
        peers = self.mock_node.config.get_peers(self.mock_node.node_id)
        for peer in peers:
            self.assertEqual(self.raft.next_index[peer], 1)  # len(log) + 1
            self.assertEqual(self.raft.match_index[peer], 0)
    
    def test_handle_request_vote_grant(self):
        """Test handling vote request - granting vote"""
        vote_data = {
            'term': 5,
            'candidate_id': 'candidate_node',
            'last_log_index': 0,
            'last_log_term': 0
        }
        
        response, status_code = self.raft._handle_request_vote(vote_data)
        
        self.assertEqual(status_code, 200)
        self.assertTrue(response['vote_granted'])
        self.assertEqual(response['term'], 5)
        self.assertEqual(self.raft.voted_for, 'candidate_node')
        self.assertEqual(self.raft.current_term, 5)
    
    def test_handle_request_vote_deny_old_term(self):
        """Test handling vote request - denying due to old term"""
        self.raft.current_term = 10
        
        vote_data = {
            'term': 5,  # Older term
            'candidate_id': 'candidate_node',
            'last_log_index': 0,
            'last_log_term': 0
        }
        
        response, status_code = self.raft._handle_request_vote(vote_data)
        
        self.assertEqual(status_code, 200)
        self.assertFalse(response['vote_granted'])
        self.assertEqual(response['term'], 10)
    
    def test_handle_request_vote_deny_already_voted(self):
        """Test handling vote request - denying because already voted"""
        self.raft.current_term = 5
        self.raft.voted_for = 'other_candidate'
        
        vote_data = {
            'term': 5,
            'candidate_id': 'candidate_node',
            'last_log_index': 0,
            'last_log_term': 0
        }
        
        response, status_code = self.raft._handle_request_vote(vote_data)
        
        self.assertEqual(status_code, 200)
        self.assertFalse(response['vote_granted'])
    
    def test_handle_append_entries_success(self):
        """Test handling append entries - success"""
        append_data = {
            'term': 5,
            'leader_id': 'leader_node',
            'prev_log_index': 0,
            'prev_log_term': 0,
            'entries': [(5, 'txn-123')],
            'leader_commit': 0
        }
        
        response, status_code = self.raft._handle_append_entries(append_data)
        
        self.assertEqual(status_code, 200)
        self.assertTrue(response['success'])
        self.assertEqual(response['term'], 5)
        self.assertEqual(self.raft.current_leader, 'leader_node')
        self.assertEqual(len(self.raft.log), 1)
    
    def test_handle_append_entries_old_term(self):
        """Test handling append entries - old term"""
        self.raft.current_term = 10
        
        append_data = {
            'term': 5,  # Older term
            'leader_id': 'leader_node',
            'prev_log_index': 0,
            'prev_log_term': 0,
            'entries': [],
            'leader_commit': 0
        }
        
        response, status_code = self.raft._handle_append_entries(append_data)
        
        self.assertEqual(status_code, 200)
        self.assertFalse(response['success'])
        self.assertEqual(response['term'], 10)
    
    def test_handle_append_entries_log_inconsistency(self):
        """Test handling append entries - log inconsistency"""
        append_data = {
            'term': 5,
            'leader_id': 'leader_node',
            'prev_log_index': 1,  # We have no log entries
            'prev_log_term': 1,
            'entries': [(5, 'txn-123')],
            'leader_commit': 0
        }
        
        response, status_code = self.raft._handle_append_entries(append_data)
        
        self.assertEqual(status_code, 200)
        self.assertFalse(response['success'])
    
    def test_is_log_up_to_date(self):
        """Test checking if candidate's log is up to date"""
        # Add some log entries
        self.raft.log = [(1, 'txn-1'), (2, 'txn-2')]
        
        # Candidate with newer term
        candidate_data = {
            'last_log_index': 1,
            'last_log_term': 3  # Newer than our last term (2)
        }
        self.assertTrue(self.raft._is_log_up_to_date(candidate_data))
        
        # Candidate with same term but fewer entries
        candidate_data = {
            'last_log_index': 1,
            'last_log_term': 2  # Same as our last term
        }
        self.assertFalse(self.raft._is_log_up_to_date(candidate_data))
        
        # Candidate with same term and same entries
        candidate_data = {
            'last_log_index': 2,
            'last_log_term': 2
        }
        self.assertTrue(self.raft._is_log_up_to_date(candidate_data))
    
    def test_is_log_consistent(self):
        """Test checking log consistency"""
        # Add some log entries
        self.raft.log = [(1, 'txn-1'), (2, 'txn-2')]
        
        # Consistent: previous entry matches
        self.assertTrue(self.raft._is_log_consistent(2, 2))
        
        # Inconsistent: term mismatch
        self.assertFalse(self.raft._is_log_consistent(2, 1))
        
        # Inconsistent: index too high
        self.assertFalse(self.raft._is_log_consistent(5, 1))
        
        # Empty log case
        self.assertTrue(self.raft._is_log_consistent(0, 0))
    
    def test_handle_peer_failure(self):
        """Test handling peer failure"""
        self.raft.current_leader = 'failed_peer'
        self.raft.state = RaftState.FOLLOWER
        
        with patch.object(self.raft, '_start_election') as mock_election:
            self.raft.handle_peer_failure('failed_peer')
            
            # Should trigger election if leader failed
            mock_election.assert_called_once()
            self.assertIsNone(self.raft.current_leader)
    
    def test_handle_peer_recovery(self):
        """Test handling peer recovery"""
        # Initialize peer tracking
        self.raft.start()
        
        # Remove peer from tracking
        del self.raft.next_index['recovered_peer']
        del self.raft.match_index['recovered_peer']
        
        self.raft.handle_peer_recovery('recovered_peer')
        
        # Should reinitialize peer tracking
        self.assertIn('recovered_peer', self.raft.next_index)
        self.assertIn('recovered_peer', self.raft.match_index)
    
    def test_get_consensus_status(self):
        """Test getting consensus status"""
        self.raft.state = RaftState.LEADER
        self.raft.current_term = 5
        self.raft.current_leader = self.mock_node.node_id
        self.raft.log = [(1, 'txn-1'), (2, 'txn-2')]
        self.raft.commit_index = 2
        
        status = self.raft.get_consensus_status()
        
        self.assertEqual(status['state'], 'leader')
        self.assertEqual(status['current_term'], 5)
        self.assertTrue(status['is_leader'])
        self.assertEqual(status['current_leader'], self.mock_node.node_id)
        self.assertEqual(status['log_length'], 2)
        self.assertEqual(status['commit_index'], 2)
    
    def test_trigger_leader_election(self):
        """Test manually triggering leader election"""
        with patch.object(self.raft, '_start_election') as mock_election:
            self.raft.trigger_leader_election()
            mock_election.assert_called_once()

if __name__ == '__main__':
    unittest.main()