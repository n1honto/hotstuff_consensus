import hashlib
import json
from typing import List, Dict, Any

class Block:
    def __init__(self, transactions: List[Dict[str, Any]], previous_hash: str, leader_id: int, round: int, shard_id: int = 0):
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.leader_id = leader_id
        self.round = round
        self.shard_id = shard_id
        self.timestamp = json.dumps({"timestamp": time.time()})
        self.hash = self.calculate_hash()

    def calculate_hash(self) -> str:
        block_string = json.dumps({
            "transactions": self.transactions,
            "previous_hash": self.previous_hash,
            "leader_id": self.leader_id,
            "round": self.round,
            "shard_id": self.shard_id,
            "timestamp": self.timestamp
        }, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transactions": self.transactions,
            "previous_hash": self.previous_hash,
            "leader_id": self.leader_id,
            "round": self.round,
            "shard_id": self.shard_id,
            "timestamp": self.timestamp,
            "hash": self.hash
        }

    def __repr__(self):
        return f"Block(hash={self.hash[:10]}..., leader={self.leader_id}, round={self.round}, shard={self.shard_id}, transactions={len(self.transactions)})"
