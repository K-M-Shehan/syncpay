# src/fault_tolerance/health_monitor.py
# Member 1: Fault Tolerance Component

import time
import threading
import requests
from typing import Dict, List
import logging
from datetime import datetime

class HealthMonitor:
    def __init__(self, node):
        self.node = node
        self.peer_status = {}  # Track peer health status
        self.health_check_interval = 10  # seconds
        self.failure_threshold = 3  # consecutive failures before marking as down
        self.is_running = False
        self.monitor_thread = None
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(f"HealthMonitor-{node.node_id}")
    
    def start(self):
        """Start health monitoring service"""
        if self.is_running:
            return
            
        self.is_running = True
        self.logger.info("Starting health monitoring service")
        
        # Initialize peer status
        peers = self.node.config.get_peers(self.node.node_id)
        for peer in peers:
            self.peer_status[peer] = {
                'is_healthy': True,
                'consecutive_failures': 0,
                'last_check': time.time(),
                'last_successful_check': time.time(),
                'response_time': 0.0
            }
        
        # Start monitoring thread
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def stop(self):
        """Stop health monitoring service"""
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join()
        self.logger.info("Health monitoring service stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.is_running:
            try:
                self._check_all_peers()
                time.sleep(self.health_check_interval)
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                time.sleep(5)  # Shorter sleep on error
    
    def _check_all_peers(self):
        """Check health of all peer nodes"""
        for peer_url in self.peer_status.keys():
            self._check_peer_health(peer_url)
    
    def _check_peer_health(self, peer_url):
        """Check health of a specific peer"""
        start_time = time.time()
        
        try:
            # Send health check request
            response = requests.get(
                f"http://{peer_url}/health",
                timeout=5,
                headers={'Content-Type': 'application/json'}
            )
            
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                # Peer is healthy
                self._mark_peer_healthy(peer_url, response_time)
                
                # Log recovery if peer was previously unhealthy
                if not self.peer_status[peer_url]['is_healthy']:
                    self.logger.info(f"Peer {peer_url} has recovered")
                    self._handle_peer_recovery(peer_url)
                    
            else:
                # Peer returned error status
                self._mark_peer_unhealthy(peer_url, f"HTTP {response.status_code}")
                
        except requests.exceptions.Timeout:
            self._mark_peer_unhealthy(peer_url, "timeout")
        except requests.exceptions.ConnectionError:
            self._mark_peer_unhealthy(peer_url, "connection_error")
        except Exception as e:
            self._mark_peer_unhealthy(peer_url, f"unknown_error: {e}")
    
    def _mark_peer_healthy(self, peer_url, response_time):
        """Mark peer as healthy"""
        peer_status = self.peer_status[peer_url]
        peer_status['is_healthy'] = True
        peer_status['consecutive_failures'] = 0
        peer_status['last_check'] = time.time()
        peer_status['last_successful_check'] = time.time()
        peer_status['response_time'] = response_time
    
    def _mark_peer_unhealthy(self, peer_url, error_reason):
        """Mark peer as potentially unhealthy"""
        peer_status = self.peer_status[peer_url]
        peer_status['consecutive_failures'] += 1
        peer_status['last_check'] = time.time()
        
        # Only mark as unhealthy after threshold failures
        if peer_status['consecutive_failures'] >= self.failure_threshold:
            if peer_status['is_healthy']:
                # First time marking as unhealthy
                peer_status['is_healthy'] = False
                self.logger.warning(f"Peer {peer_url} marked as unhealthy: {error_reason}")
                self._handle_peer_failure(peer_url)
            
        else:
            self.logger.debug(f"Peer {peer_url} check failed ({peer_status['consecutive_failures']}/{self.failure_threshold}): {error_reason}")
    
    def _handle_peer_failure(self, peer_url):
        """Handle detected peer failure"""
        self.logger.error(f"PEER FAILURE DETECTED: {peer_url}")
        
        # Trigger failover mechanisms
        self._trigger_failover(peer_url)
        
        # Notify other components about the failure
        self._notify_failure(peer_url)
    
    def _handle_peer_recovery(self, peer_url):
        """Handle peer recovery"""
        self.logger.info(f"PEER RECOVERY DETECTED: {peer_url}")
        
        # Notify other components about recovery
        self._notify_recovery(peer_url)
        
        # Trigger replication sync if needed
        if hasattr(self.node, 'replicator'):
            self.node.replicator.sync_with_recovered_peer(peer_url)
    
    def _trigger_failover(self, failed_peer_url):
        """Trigger failover mechanisms when a peer fails"""
        # If the failed peer was the leader, trigger leader election
        if hasattr(self.node, 'consensus'):
            if self.node.consensus.current_leader == failed_peer_url:
                self.logger.info("Failed peer was leader, triggering election")
                self.node.consensus.trigger_leader_election()
        
        # Update routing to avoid failed peer
        healthy_peers = self.get_healthy_peers()
        if len(healthy_peers) == 0:
            self.logger.critical("ALL PEERS ARE DOWN - SYSTEM IN DEGRADED MODE")
            # Still continue operating but log critical status
    
    def _notify_failure(self, peer_url):
        """Notify other components about peer failure"""
        # Notify consensus component
        if hasattr(self.node, 'consensus'):
            self.node.consensus.handle_peer_failure(peer_url)
        
        # Notify replication component  
        if hasattr(self.node, 'replicator'):
            self.node.replicator.handle_peer_failure(peer_url)
    
    def _notify_recovery(self, peer_url):
        """Notify other components about peer recovery"""
        # Notify consensus component
        if hasattr(self.node, 'consensus'):
            self.node.consensus.handle_peer_recovery(peer_url)
        
        # Notify replication component
        if hasattr(self.node, 'replicator'):
            self.node.replicator.handle_peer_recovery(peer_url)
    
    def get_healthy_peers(self) -> List[str]:
        """Get list of currently healthy peers"""
        return [
            peer for peer, status in self.peer_status.items()
            if status['is_healthy']
        ]
    
    def get_peer_status(self) -> Dict:
        """Get current status of all peers"""
        status_summary = {}
        for peer, status in self.peer_status.items():
            status_summary[peer] = {
                'healthy': status['is_healthy'],
                'consecutive_failures': status['consecutive_failures'],
                'last_check_ago': time.time() - status['last_check'],
                'response_time_ms': status['response_time'] * 1000
            }
        return status_summary
    
    def is_cluster_healthy(self) -> bool:
        """Check if cluster has minimum healthy nodes"""
        healthy_count = len(self.get_healthy_peers()) + 1  # +1 for current node
        total_nodes = len(self.peer_status) + 1
        
        # Require at least majority of nodes to be healthy
        return healthy_count >= (total_nodes // 2 + 1)
    
    def get_best_peer_for_request(self) -> str:
        """Get the healthiest peer for routing requests"""
        healthy_peers = self.get_healthy_peers()
        
        if not healthy_peers:
            return None
        
        # Choose peer with lowest response time
        best_peer = min(
            healthy_peers,
            key=lambda peer: self.peer_status[peer]['response_time']
        )
        
        return best_peer
