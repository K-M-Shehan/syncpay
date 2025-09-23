import json
from typing import List, Dict

class Config:
    def __init__(self, config_file: str = None):
        self.node_configs = {
            "node1": {"host": "localhost", "port": 5000},
            "node2": {"host": "localhost", "port": 5001},  
            "node3": {"host": "localhost", "port": 5002}
        }
        self.consensus_timeout = 5.0
        self.health_check_interval = 10.0
        self.replication_timeout = 2.0
        
        if config_file:
            self.load_from_file(config_file)
    
    def load_from_file(self, file_path: str):
        with open(file_path, 'r') as f:
            data = json.load(f)
            self.__dict__.update(data)
    
    def get_peers(self, current_node: str) -> List[str]:
        peers = []
        for node_id, config in self.node_configs.items():
            if node_id != current_node:
                peers.append(f"{config['host']}:{config['port']}")
        return peers
