import hashlib
import json
from typing import List, Dict

class Block:
    def __init__(self, transactions: List[Dict], previous_hash: str, leader_id: int, round: int, shard_id: int = 0):
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.leader_id = leader_id
        self.round = round
        self.shard_id = shard_id
        self.hash = self.calculate_hash()

    def calculate_hash(self) -> str:
        block_string = json.dumps({
            "transactions": self.transactions,
            "previous_hash": self.previous_hash,
            "leader_id": self.leader_id,
            "round": self.round,
            "shard_id": self.shard_id
        }, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def __repr__(self):
        return f"Block(hash={self.hash}, leader={self.leader_id}, round={self.round}, shard={self.shard_id}, transactions={len(self.transactions)})"
