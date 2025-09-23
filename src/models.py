from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
import time
import uuid

@dataclass
class PaymentTransaction:
    id: str
    amount: float
    sender: str
    receiver: str
    timestamp: float
    status: str = "pending"
    node_id: str = ""
    
    @classmethod
    def create(cls, amount: float, sender: str, receiver: str, node_id: str):
        return cls(
            id=str(uuid.uuid4()),
            amount=amount,
            sender=sender,
            receiver=receiver,
            timestamp=time.time(),
            node_id=node_id
        )
    
    def to_dict(self):
        return asdict(self)

@dataclass
class NodeInfo:
    node_id: str
    host: str
    port: int
    is_leader: bool = False
    is_healthy: bool = True
    last_heartbeat: float = 0.0
