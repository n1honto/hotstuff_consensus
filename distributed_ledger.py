
import json
import time
import hashlib
from typing import Dict, List, Any, Optional
from collections import defaultdict
from transaction import Transaction

class DistributedLedger:
    def __init__(self):
        self.blockchain: List[Dict[str, Any]] = []
        self.pending_transactions: List[Transaction] = []
        self.transaction_map: Dict[str, Transaction] = {}
        self.transaction_links: Dict[str, List[str]] = defaultdict(list)
        self.balances: Dict[str, float] = defaultdict(float)

    def add_transaction(self, transaction: Transaction):
        self.pending_transactions.append(transaction)
        self.transaction_map[transaction.hash] = transaction

    def link_transactions(self, hash1: str, hash2: str):
        self.transaction_links[hash1].append(hash2)
        self.transaction_links[hash2].append(hash1)

    def get_linked_transactions(self, transaction_hash: str) -> List[Transaction]:
        return [self.transaction_map[tx_hash] for tx_hash in self.transaction_links[transaction_hash]]

    def validate_transaction(self, transaction: Transaction) -> bool:
        if transaction.sender not in self.balances:
            return False
        if self.balances[transaction.sender] < transaction.amount:
            return False
        return True

    def apply_transaction(self, transaction: Transaction):
        if transaction.sender in self.balances:
            self.balances[transaction.sender] -= transaction.amount
        else:
            self.balances[transaction.sender] = -transaction.amount

        if transaction.receiver in self.balances:
            self.balances[transaction.receiver] += transaction.amount
        else:
            self.balances[transaction.receiver] = transaction.amount

    def create_block(self, transactions: List[Transaction], leader_id: int, round: int) -> Dict[str, Any]:
        block = {
            "index": len(self.blockchain) + 1,
            "timestamp": time.time(),
            "transactions": [tx.to_dict() for tx in transactions],
            "leader_id": leader_id,
            "round": round,
            "previous_hash": self.blockchain[-1]["hash"] if self.blockchain else "0"
        }
        block["hash"] = self.calculate_block_hash(block)
        return block

    def calculate_block_hash(self, block: Dict[str, Any]) -> str:
        block_copy = block.copy()
        block_copy.pop("hash", None)
        block_string = json.dumps(block_copy, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def add_block(self, block: Dict[str, Any]):
        self.blockchain.append(block)
        for tx_dict in block["transactions"]:
            tx = Transaction(tx_dict["from"], tx_dict["to"], tx_dict["amount"])
            tx.timestamp = tx_dict["timestamp"]
            tx.signature = tx_dict["signature"]
            tx.hash = tx_dict["hash"]
            self.apply_transaction(tx)
        self.pending_transactions = []

    def get_balance(self, user: str) -> float:
        return self.balances.get(user, 0)

    def get_transaction(self, transaction_hash: str) -> Optional[Transaction]:
        return self.transaction_map.get(transaction_hash)

    def get_block(self, block_hash: str) -> Optional[Dict[str, Any]]:
        for block in self.blockchain:
            if block["hash"] == block_hash:
                return block
        return None

    def get_block_by_index(self, index: int) -> Optional[Dict[str, Any]]:
        if 0 <= index < len(self.blockchain):
            return self.blockchain[index]
        return None
