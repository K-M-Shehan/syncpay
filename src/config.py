import json
import os
from typing import List, Dict, Any, Optional

class Config:
    """Configuration manager for SyncPay nodes"""
    
    def __init__(self, config_file: str = None):
        # Default configuration
        self.node_configs = {
            "node1": {"host": "localhost", "port": 5000},
            "node2": {"host": "localhost", "port": 5001},  
            "node3": {"host": "localhost", "port": 5002}
        }
        
        # Consensus settings
        self.consensus_timeout = 5.0
        self.consensus_heartbeat_interval = 1.0
        self.consensus_election_timeout_min = 5.0
        self.consensus_election_timeout_max = 10.0
        
        # Health monitoring settings
        self.health_check_interval = 10.0
        self.health_failure_threshold = 3
        self.health_check_timeout = 5.0
        
        # Replication settings
        self.replication_timeout = 5.0
        self.replication_max_retries = 3
        self.replication_retry_delay = 1.0
        self.replication_batch_size = 10
        self.replication_worker_count = 3
        
        # Time synchronization settings
        self.time_sync_interval = 30.0
        self.time_sync_timeout = 5.0
        self.time_sync_min_samples = 3
        self.time_sync_max_samples = 10
        
        # Payment limits
        self.payment_max_amount = 1000000.0
        self.payment_max_name_length = 100
        
        # Performance settings
        self.http_pool_connections = 10
        self.http_pool_maxsize = 20
        
        # Load from file if provided
        if config_file:
            self.load_from_file(config_file)
        
        # Load from environment variables (overrides file config)
        self.load_from_env()
    
    def load_from_file(self, file_path: str):
        """Load configuration from JSON file"""
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                self.__dict__.update(data)
        except FileNotFoundError:
            print(f"Warning: Config file {file_path} not found, using defaults")
        except json.JSONDecodeError as e:
            print(f"Warning: Error parsing config file: {e}, using defaults")
    
    def load_from_env(self):
        """Load configuration from environment variables"""
        # Node configurations
        if os.getenv('SYNCPAY_NODE_CONFIGS'):
            try:
                self.node_configs = json.loads(os.getenv('SYNCPAY_NODE_CONFIGS'))
            except json.JSONDecodeError:
                pass
        
        # Timeouts
        if os.getenv('SYNCPAY_CONSENSUS_TIMEOUT'):
            self.consensus_timeout = float(os.getenv('SYNCPAY_CONSENSUS_TIMEOUT'))
        
        if os.getenv('SYNCPAY_HEALTH_CHECK_INTERVAL'):
            self.health_check_interval = float(os.getenv('SYNCPAY_HEALTH_CHECK_INTERVAL'))
        
        if os.getenv('SYNCPAY_REPLICATION_TIMEOUT'):
            self.replication_timeout = float(os.getenv('SYNCPAY_REPLICATION_TIMEOUT'))
    
    def get_peers(self, current_node: str) -> List[str]:
        """Get list of peer URLs for a given node"""
        peers = []
        for node_id, config in self.node_configs.items():
            if node_id != current_node:
                peers.append(f"{config['host']}:{config['port']}")
        return peers
    
    def get_node_url(self, node_id: str) -> Optional[str]:
        """Get the URL for a specific node"""
        if node_id in self.node_configs:
            config = self.node_configs[node_id]
            return f"{config['host']}:{config['port']}"
        return None
    
    def get_all_node_urls(self) -> List[str]:
        """Get URLs for all configured nodes"""
        return [f"{config['host']}:{config['port']}" 
                for config in self.node_configs.values()]
    
    def to_dict(self) -> Dict[str, Any]:
        """Export configuration as dictionary"""
        return {k: v for k, v in self.__dict__.items() 
                if not k.startswith('_')}
    
    def save_to_file(self, file_path: str):
        """Save current configuration to file"""
        with open(file_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
