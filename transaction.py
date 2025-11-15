import json
import time
import hashlib
from typing import Dict, Any

class Transaction:
    def __init__(self, sender: str, receiver: str, amount: float):
        self.sender = sender
        self.receiver = receiver
        self.amount = amount
        self.timestamp = time.time()
        self.signature = self._generate_signature()
        self.hash = self._generate_hash()

    def _generate_signature(self) -> str:
        tx_string = json.dumps({
            "sender": self.sender,
            "receiver": self.receiver,
            "amount": self.amount,
            "timestamp": self.timestamp
        }, sort_keys=True).encode()
        return hashlib.sha256(tx_string).hexdigest()

    def _generate_hash(self) -> str:
        tx_string = json.dumps({
            "sender": self.sender,
            "receiver": self.receiver,
            "amount": self.amount,
            "timestamp": self.timestamp,
            "signature": self.signature
        }, sort_keys=True).encode()
        return hashlib.sha256(tx_string).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from": self.sender,
            "to": self.receiver,
            "amount": self.amount,
            "timestamp": self.timestamp,
            "signature": self.signature,
            "hash": self.hash
        }

    def __repr__(self):
        return f"Transaction(hash={self.hash[:10]}..., from={self.sender}, to={self.receiver}, amount={self.amount})"
