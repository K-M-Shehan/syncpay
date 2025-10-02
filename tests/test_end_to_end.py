# tests/test_end_to_end.py
# End-to-end tests using real HTTP requests

import unittest
import time
import requests
import threading
import subprocess
import signal
import os
import sys
import json
from pathlib import Path

class TestSyncPayEndToEnd(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        """Start SyncPay cluster for testing"""
        cls.base_dir = Path(__file__).parent.parent
        cls.processes = []
        cls.node_urls = {
            'node1': 'http://localhost:5000',
            'node2': 'http://localhost:5001', 
            'node3': 'http://localhost:5002'
        }
        
        # Start nodes
        cls._start_cluster()
        
        # Wait for nodes to start
        time.sleep(10)
        
        # Verify nodes are running
        cls._wait_for_nodes()
    
    @classmethod
    def _start_cluster(cls):
        """Start the SyncPay cluster"""
        src_dir = cls.base_dir / 'src'
        venv_python = cls.base_dir / 'syncpay_env' / 'bin' / 'python3'
        
        for node_id in ['node1', 'node2', 'node3']:
            cmd = [str(venv_python), 'main.py', node_id]
            
            process = subprocess.Popen(
                cmd,
                cwd=src_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid  # Create new process group
            )
            cls.processes.append(process)
            time.sleep(3)  # Stagger startup
    
    @classmethod
    def _wait_for_nodes(cls):
        """Wait for all nodes to be healthy"""
        max_attempts = 30
        for attempt in range(max_attempts):
            all_healthy = True
            for node_id, url in cls.node_urls.items():
                try:
                    response = requests.get(f"{url}/health", timeout=2)
                    if response.status_code != 200:
                        all_healthy = False
                        break
                except:
                    all_healthy = False
                    break
            
            if all_healthy:
                print(f"All nodes healthy after {attempt + 1} attempts")
                return
            
            time.sleep(2)
        
        raise Exception("Nodes failed to start within timeout")
    
    @classmethod
    def tearDownClass(cls):
        """Stop the SyncPay cluster"""
        for process in cls.processes:
            try:
                # Kill process group to ensure all child processes are terminated
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                process.wait(timeout=5)
            except:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except:
                    pass
    
    def test_node_health_check(self):
        """Test health check endpoints"""
        for node_id, url in self.node_urls.items():
            response = requests.get(f"{url}/health")
            
            self.assertEqual(response.status_code, 200)
            data = response.json()
            
            self.assertEqual(data['node_id'], node_id)
            self.assertEqual(data['status'], 'healthy')
            self.assertIn('timestamp', data)
            self.assertIn('transaction_count', data)
    
    def test_node_status_check(self):
        """Test status endpoints"""
        for node_id, url in self.node_urls.items():
            response = requests.get(f"{url}/status")
            
            self.assertEqual(response.status_code, 200)
            data = response.json()
            
            self.assertEqual(data['node_id'], node_id)
            self.assertIn('is_leader', data)
            self.assertIn('peer_health', data)
            self.assertIn('replication_status', data)
            self.assertIn('time_offset', data)
    
    def test_leader_election(self):
        """Test that exactly one leader is elected"""
        leaders = []
        
        for node_id, url in self.node_urls.items():
            response = requests.get(f"{url}/status")
            data = response.json()
            
            if data['is_leader']:
                leaders.append(node_id)
        
        # Should have exactly one leader
        self.assertEqual(len(leaders), 1, f"Expected 1 leader, found {len(leaders)}: {leaders}")
    
    def test_payment_transaction(self):
        """Test processing a payment transaction"""
        transaction_id = self._create_test_payment()
        self.assertIsNotNone(transaction_id, "Transaction ID should be returned")
    
    def _create_test_payment(self):
        """Helper method to create a test payment transaction"""
        # Find the leader
        leader_url = None
        for node_id, url in self.node_urls.items():
            response = requests.get(f"{url}/status")
            data = response.json()
            if data['is_leader']:
                leader_url = url
                break
        
        self.assertIsNotNone(leader_url, "No leader found")
        
        # Submit payment to leader
        payment_data = {
            'amount': 150.75,
            'sender': 'alice',
            'receiver': 'bob'
        }
        
        response = requests.post(
            f"{leader_url}/payment",
            json=payment_data,
            headers={'Content-Type': 'application/json'}
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data['status'], 'success')
        self.assertIn('transaction_id', data)
        self.assertIn('timestamp', data)
        self.assertIn('processed_by', data)
        
        return data['transaction_id']
    
    def test_transaction_replication(self):
        """Test that transactions are replicated across nodes"""
        # Process a transaction using helper method
        transaction_id = self._create_test_payment()
        
        # Wait for replication with polling
        max_wait = 15  # seconds
        wait_interval = 1  # seconds
        transaction_found_count = 0
        
        for attempt in range(max_wait):
            transaction_found_count = 0
            
            for node_id, url in self.node_urls.items():
                try:
                    response = requests.get(f"{url}/transactions", timeout=5)
                    self.assertEqual(response.status_code, 200)
                    
                    data = response.json()
                    transactions = data['transactions']
                    
                    # Check if our transaction is in this node
                    found = any(txn['id'] == transaction_id for txn in transactions)
                    if found:
                        transaction_found_count += 1
                except Exception as e:
                    # Node might be temporarily unavailable
                    print(f"Warning: Could not check {node_id}: {e}")
                    continue
            
            # If we have majority replication, we're done
            if transaction_found_count >= 2:
                break
                
            time.sleep(wait_interval)
        
        # Transaction should be on all nodes (or at least majority)
        self.assertGreaterEqual(transaction_found_count, 2, 
                               f"Transaction replicated to {transaction_found_count}/3 nodes after {max_wait}s wait")
    
    def test_multiple_transactions(self):
        """Test processing multiple transactions"""
        # Find the leader
        leader_url = None
        for node_id, url in self.node_urls.items():
            response = requests.get(f"{url}/status")
            data = response.json()
            if data['is_leader']:
                leader_url = url
                break
        
        transaction_ids = []
        
        # Submit multiple transactions
        for i in range(5):
            payment_data = {
                'amount': 100.0 + i,
                'sender': f'user{i}',
                'receiver': f'merchant{i}'
            }
            
            response = requests.post(
                f"{leader_url}/payment",
                json=payment_data,
                headers={'Content-Type': 'application/json'}
            )
            
            self.assertEqual(response.status_code, 200)
            data = response.json()
            transaction_ids.append(data['transaction_id'])
            
            time.sleep(1)  # Brief pause between transactions
        
        # Wait for replication
        time.sleep(10)
        
        # Verify all transactions are on leader
        response = requests.get(f"{leader_url}/transactions")
        data = response.json()
        leader_transactions = {txn['id'] for txn in data['transactions']}
        
        for txn_id in transaction_ids:
            self.assertIn(txn_id, leader_transactions)
        
        # Allow extra time for replication to catch up
        time.sleep(5)
    
    def test_time_synchronization(self):
        """Test time synchronization across nodes"""
        timestamps = []
        
        # Get synchronized time from all nodes
        for node_id, url in self.node_urls.items():
            response = requests.get(f"{url}/health")
            data = response.json()
            timestamps.append(data['timestamp'])
        
        # All timestamps should be close to each other
        max_timestamp = max(timestamps)
        min_timestamp = min(timestamps)
        
        # Should be within 1 second of each other
        self.assertLess(max_timestamp - min_timestamp, 1.0,
                       "Node timestamps are not synchronized")
    
    def test_peer_health_monitoring(self):
        """Test peer health monitoring"""
        for node_id, url in self.node_urls.items():
            response = requests.get(f"{url}/status")
            data = response.json()
            
            peer_health = data['peer_health']
            
            # Should have status for other nodes
            expected_peer_count = len(self.node_urls) - 1
            self.assertEqual(len(peer_health), expected_peer_count)
            
            # All peers should be healthy
            for peer, status in peer_health.items():
                self.assertTrue(status['healthy'], f"Peer {peer} is not healthy")
    
    def test_consensus_metrics(self):
        """Test consensus-related metrics"""
        leader_node = None
        follower_count = 0
        
        for node_id, url in self.node_urls.items():
            response = requests.get(f"{url}/status")
            data = response.json()
            
            if data['is_leader']:
                leader_node = node_id
            else:
                follower_count += 1
        
        # Should have 1 leader and 2 followers
        self.assertIsNotNone(leader_node)
        self.assertEqual(follower_count, 2)
    
    def test_invalid_payment_data(self):
        """Test handling of invalid payment data"""
        # Find the leader
        leader_url = None
        for node_id, url in self.node_urls.items():
            response = requests.get(f"{url}/status")
            data = response.json()
            if data['is_leader']:
                leader_url = url
                break
        
        # Test missing fields
        invalid_data = {'amount': 100.0}  # Missing sender and receiver
        
        response = requests.post(
            f"{leader_url}/payment",
            json=invalid_data,
            headers={'Content-Type': 'application/json'}
        )
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
    
    def test_system_load(self):
        """Test system under moderate load"""
        # Find the leader
        leader_url = None
        for node_id, url in self.node_urls.items():
            response = requests.get(f"{url}/status")
            data = response.json()
            if data['is_leader']:
                leader_url = url
                break
        
        # Submit transactions concurrently
        import concurrent.futures
        
        def submit_transaction(i):
            payment_data = {
                'amount': 50.0 + (i % 100),
                'sender': f'user{i}',
                'receiver': f'merchant{i % 10}'
            }
            
            response = requests.post(
                f"{leader_url}/payment",
                json=payment_data,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            return response.status_code == 200
        
        # Submit 20 transactions concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(submit_transaction, i) for i in range(20)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        # Most transactions should succeed
        success_rate = sum(results) / len(results)
        self.assertGreater(success_rate, 0.8, f"Success rate too low: {success_rate}")
        
        # Allow extra time for replication to catch up after heavy load
        time.sleep(20)

if __name__ == '__main__':
    # Only run if explicitly requested (these tests start real servers)
    if len(sys.argv) > 1 and sys.argv[1] == '--e2e':
        unittest.main(argv=[''])
    else:
        print("Skipping end-to-end tests. Use --e2e flag to run them.")
        print("Example: python test_end_to_end.py --e2e")