# src/time_sync/time_synchronizer.py
# Member 3: Time Synchronization Component

import time
import threading
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import statistics
from typing import Dict, List, Optional
import logging
from datetime import datetime

class TimeSynchronizer:
    def __init__(self, node):
        self.node = node

        # Time synchronization state
        self.time_offset = 0.0  # Offset from system time to synchronized time
        self.clock_skew = 0.0   # Estimated clock skew
        self.sync_accuracy = 0.0  # Estimated synchronization accuracy in milliseconds

        # Synchronization parameters
        self.sync_interval = 30.0  # seconds between sync attempts
        self.sync_timeout = 5.0    # timeout for sync requests
        self.min_samples = 3       # minimum samples for offset calculation
        self.max_samples = 10      # maximum samples to keep
        self.outlier_threshold = 2.0  # threshold for outlier detection (in standard deviations)

        # Sample storage for statistical analysis
        self.time_samples = []  # List of (peer_time, local_time, round_trip_time) tuples
        self.peer_offsets = {}   # peer -> list of calculated offsets

        # Threading
        self.is_running = False
        self.sync_thread = None

        # HTTP Session for better performance
        self.session = self._create_session()

        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(f"TimeSync-{node.node_id}")

    def _create_session(self) -> requests.Session:
        """Create a requests session with connection pooling"""
        session = requests.Session()
        
        adapter = HTTPAdapter(
            pool_connections=5,
            pool_maxsize=10,
            max_retries=0,  # We handle retries manually
            pool_block=False
        )
        
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session

    def start(self):
        """Start the time synchronization service"""
        if self.is_running:
            return

        self.is_running = True
        self.logger.info("Starting time synchronization service")

        # Perform initial synchronization
        self._perform_initial_sync()

        # Start periodic synchronization thread
        self.sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self.sync_thread.start()

    def stop(self):
        """Stop the time synchronization service"""
        self.is_running = False
        if self.sync_thread:
            self.sync_thread.join(timeout=5.0)
        
        # Close session to release connections
        if hasattr(self, 'session'):
            self.session.close()
            
        self.logger.info("Time synchronization service stopped")

    def get_synchronized_time(self) -> float:
        """Get the current synchronized time"""
        return time.time() + self.time_offset

    def get_time_offset(self) -> float:
        """Get the current time offset in milliseconds"""
        return self.time_offset * 1000

    def get_sync_status(self) -> Dict:
        """Get current synchronization status"""
        current_time = time.time()

        return {
            'time_offset_ms': self.get_time_offset(),
            'clock_skew_ppm': self.clock_skew * 1e6,  # parts per million
            'sync_accuracy_ms': self.sync_accuracy * 1000,
            'last_sync_time': getattr(self, 'last_sync_time', 0),
            'time_since_last_sync': current_time - getattr(self, 'last_sync_time', 0),
            'sample_count': len(self.time_samples),
            'peer_count': len(self.peer_offsets)
        }

    def _sync_loop(self):
        """Main synchronization loop"""
        while self.is_running:
            try:
                self._perform_sync_round()
                time.sleep(self.sync_interval)
            except Exception as e:
                self.logger.error(f"Error in sync loop: {e}")
                time.sleep(5.0)  # Shorter sleep on error

    def _perform_initial_sync(self):
        """Perform initial time synchronization"""
        self.logger.info("Performing initial time synchronization")

        # Try to sync with all peers
        peers = self.node.config.get_peers(self.node.node_id)
        if not peers:
            self.logger.warning("No peers available for initial sync")
            return

        # Perform multiple rounds for better accuracy
        for round_num in range(3):
            self.logger.debug(f"Initial sync round {round_num + 1}/3")
            self._perform_sync_round()

            if len(self.time_samples) >= self.min_samples:
                self._calculate_offset()
                break

            time.sleep(2.0)  # Brief pause between rounds

        self.logger.info(f"Initial sync completed. Offset: {self.time_offset:.3f}s")

    def _perform_sync_round(self):
        """Perform one round of synchronization with all peers"""
        peers = self.node.config.get_peers(self.node.node_id)
        if not peers:
            return

        self.logger.debug(f"Starting sync round with {len(peers)} peers")

        # Sync with each peer
        for peer in peers:
            try:
                offset = self._sync_with_peer(peer)
                if offset is not None:
                    if peer not in self.peer_offsets:
                        self.peer_offsets[peer] = []
                    self.peer_offsets[peer].append(offset)

                    # Keep only recent samples
                    if len(self.peer_offsets[peer]) > self.max_samples:
                        self.peer_offsets[peer].pop(0)

            except Exception as e:
                self.logger.warning(f"Failed to sync with peer {peer}: {e}")

        # Calculate new offset if we have enough samples
        if self._has_enough_samples():
            self._calculate_offset()
            self.last_sync_time = time.time()

    def _sync_with_peer(self, peer: str) -> Optional[float]:
        """
        Perform NTP-style time synchronization with a peer
        Returns the calculated offset or None if sync failed
        """
        try:
            # Send multiple requests to calculate round-trip time
            offsets = []
            rtts = []

            for attempt in range(3):  # 3 attempts for statistical accuracy
                t1 = time.time()  # Local time before request

                response = self.session.post(
                    f"http://{peer}/time_sync",
                    json={
                        't1': t1,
                        'node_id': self.node.node_id
                    },
                    timeout=self.sync_timeout
                )

                t4 = time.time()  # Local time after response

                if response.status_code == 200:
                    data = response.json()
                    t2 = data.get('t2')  # Peer time when request received
                    t3 = data.get('t3')  # Peer time when response sent

                    if t2 and t3:
                        # Calculate offset using NTP algorithm
                        # Offset = ((t2 - t1) + (t3 - t4)) / 2
                        offset = ((t2 - t1) + (t3 - t4)) / 2
                        rtt = (t4 - t1) - (t3 - t2)  # Round-trip time

                        offsets.append(offset)
                        rtts.append(rtt)
                    else:
                        self.logger.warning(f"Invalid time sync response from {peer}")
                else:
                    self.logger.warning(f"Time sync request to {peer} failed: HTTP {response.status_code}")

            if offsets:
                # Use median to reduce outlier effects
                median_offset = statistics.median(offsets)
                median_rtt = statistics.median(rtts)

                # Store sample for later analysis
                self.time_samples.append((median_offset, time.time(), median_rtt))

                # Keep only recent samples
                if len(self.time_samples) > self.max_samples:
                    self.time_samples.pop(0)

                return median_offset

        except requests.exceptions.Timeout:
            self.logger.debug(f"Time sync timeout with {peer}")
        except requests.exceptions.ConnectionError:
            self.logger.debug(f"Connection error syncing with {peer}")
        except Exception as e:
            self.logger.error(f"Unexpected error syncing with {peer}: {e}")

        return None

    def _has_enough_samples(self) -> bool:
        """Check if we have enough samples for reliable offset calculation"""
        total_samples = sum(len(samples) for samples in self.peer_offsets.values())
        return total_samples >= self.min_samples

    def _calculate_offset(self):
        """Calculate time offset from collected samples"""
        if not self.time_samples:
            return

        # Extract offsets from recent samples
        recent_offsets = [sample[0] for sample in self.time_samples[-self.max_samples:]]

        if len(recent_offsets) < self.min_samples:
            return

        # Remove outliers using statistical method
        filtered_offsets = self._filter_outliers(recent_offsets)

        if not filtered_offsets:
            filtered_offsets = recent_offsets

        # Calculate weighted average (more recent samples have higher weight)
        weights = list(range(1, len(filtered_offsets) + 1))
        total_weight = sum(weights)

        weighted_offset = sum(offset * weight for offset, weight in zip(filtered_offsets, weights)) / total_weight

        # Update offset with some smoothing to avoid sudden jumps
        smoothing_factor = 0.3
        old_offset = self.time_offset
        self.time_offset = (1 - smoothing_factor) * old_offset + smoothing_factor * weighted_offset

        # Calculate clock skew (rate of change of offset)
        if hasattr(self, 'previous_offset_time'):
            time_diff = time.time() - self.previous_offset_time
            if time_diff > 0:
                offset_change = self.time_offset - old_offset
                self.clock_skew = offset_change / time_diff

        self.previous_offset_time = time.time()

        # Estimate synchronization accuracy
        if len(filtered_offsets) > 1:
            self.sync_accuracy = statistics.stdev(filtered_offsets) / 2  # Half the standard deviation

        self.logger.debug(f"Calculated offset: {self.time_offset:.3f}s, accuracy: {self.sync_accuracy:.3f}s")

    def _filter_outliers(self, offsets: List[float]) -> List[float]:
        """Filter out outlier offsets using statistical method"""
        if len(offsets) < 3:
            return offsets

        mean = statistics.mean(offsets)
        stdev = statistics.stdev(offsets)

        # Keep only values within threshold standard deviations
        filtered = [offset for offset in offsets
                   if abs(offset - mean) <= self.outlier_threshold * stdev]

        return filtered

    def handle_sync_request(self, request) -> tuple[Dict, int]:
        """
        Handle incoming time synchronization requests
        Returns (response_dict, status_code)
        """
        try:
            data = request.get_json()

            if not data or 't1' not in data:
                return {"error": "Missing t1 timestamp"}, 400

            t1 = data['t1']  # Client time when request was sent
            source_node = data.get('node_id', 'unknown')

            # Get current time (t2 and t3 are the same for simplicity)
            t2 = t3 = time.time()

            self.logger.debug(f"Time sync request from {source_node}")

            return {
                "t2": t2,  # Time when request was received
                "t3": t3,  # Time when response is sent
                "server_time": self.get_synchronized_time(),
                "offset_ms": self.get_time_offset()
            }, 200

        except Exception as e:
            self.logger.error(f"Error handling time sync request: {e}")
            return {"error": str(e)}, 500

    def force_sync(self):
        """Force an immediate synchronization round"""
        self.logger.info("Forcing immediate time synchronization")
        self._perform_sync_round()

    def reset_sync(self):
        """Reset synchronization state (for testing/debugging)"""
        self.time_offset = 0.0
        self.clock_skew = 0.0
        self.sync_accuracy = 0.0
        self.time_samples.clear()
        self.peer_offsets.clear()
        self.logger.info("Time synchronization state reset")