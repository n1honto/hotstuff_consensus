import asyncio
import json
import random
import time
import psutil
from typing import List, Dict, Optional, Set, Tuple
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from cryptography.fernet import Fernet
from block import Block
from logger import setup_logger

class HotStuffNode:
    def __init__(self, node_id: int, nodes: List[int], host: str, port: int, shard_id: int = 0, is_byzantine: bool = False):
        self.node_id = node_id
        self.nodes = set(nodes)
        self.host = host
        self.port = port
        self.shard_id = shard_id
        self.is_byzantine = is_byzantine
        self.current_leader = 0
        self.current_round = 0
        self.blockchain: List[Block] = []
        self.prepare_votes: Dict[int, bool] = {}
        self.precommit_votes: Dict[int, bool] = {}
        self.commit_votes: Dict[int, bool] = {}
        self.current_block: Optional[Block] = None
        self.locked_round = -1
        self.locked_block: Optional[Block] = None
        self.logger = setup_logger(node_id)
        self.logger.info(f"Node {self.node_id} initialized")
        self.recovery_data: Dict = {}
        self.byzantine_nodes: Set[int] = set()
        self.checkpoints: Dict[int, Block] = {}
        self.checkpoint_interval = 5
        self.behavior_scores: Dict[int, int] = defaultdict(int)
        self.message_batch: List[Dict] = []
        self.batch_interval = 0.1
        self.last_batch_time = time.time()
        self.recovery_requests: Set[Tuple[int, int]] = set()
        self.metrics = defaultdict(list)
        self.monitor = None
        self.fernet = Fernet(Fernet.generate_key())
        self.shard_leaders: Dict[int, int] = {}
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.loop = asyncio.get_event_loop()
        self.latency_times: Dict[int, List[float]] = defaultdict(list)
        self.shard_load: Dict[int, int] = defaultdict(int)
        self.last_shard_adjustment = time.time()
        self.shard_adjustment_interval = 30

    async def propose_block(self, transactions: List[Dict]) -> Block:
        previous_hash = self.blockchain[-1].hash if self.blockchain else "0"
        block = Block(transactions, previous_hash, self.current_leader, self.current_round, self.shard_id)
        self.current_block = block
        self.logger.info(f"Proposed block: {block}")
        return block

    async def encrypt_message(self, message: Dict) -> bytes:
        return self.fernet.encrypt(json.dumps(message).encode())

    async def decrypt_message(self, encrypted: bytes) -> Dict:
        return json.loads(self.fernet.decrypt(encrypted).decode())

    async def send_message(self, message: Dict, recipient_id: int):
        if recipient_id in self.byzantine_nodes:
            self.logger.warning(f"Skipping Byzantine node {recipient_id}")
            return
        try:
            start_time = time.time()
            encrypted = self.fernet.encrypt(json.dumps(message).encode())
            self.message_batch.append((recipient_id, encrypted, start_time))
            current_time = time.time()
            if current_time - self.last_batch_time >= self.batch_interval:
                await self.flush_message_batch()
        except Exception as e:
            self.logger.error(f"Error batching message to Node {recipient_id}: {e}")

    async def flush_message_batch(self):
        if not self.message_batch:
            return
        batch = defaultdict(list)
        for recipient_id, encrypted, start_time in self.message_batch:
            batch[recipient_id].append((encrypted, start_time))
        self.message_batch.clear()
        self.last_batch_time = time.time()

        for recipient_id, messages in batch.items():
            try:
                reader, writer = await asyncio.open_connection(self.host, 5000 + recipient_id)
                for encrypted, start_time in messages:
                    writer.write(len(encrypted).to_bytes(4, "big") + encrypted)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                self.logger.debug(f"Sent batch of {len(messages)} messages to Node {recipient_id}")
                self.metrics["messages_sent"].append((time.time(), len(messages)))
                if self.monitor:
                    self.monitor.log_metric(self.node_id, "messages_sent", len(messages))
                for _, start_time in messages:
                    latency = time.time() - start_time
                    self.latency_times[recipient_id].append(latency)
                    if self.monitor:
                        self.monitor.log_metric(self.node_id, "latency", latency)
            except Exception as e:
                self.logger.error(f"Failed to send batch to Node {recipient_id}: {e}")
                self.byzantine_nodes.add(recipient_id)
                self.behavior_scores[recipient_id] += 1
                if self.behavior_scores[recipient_id] > 3:
                    self.logger.warning(f"Node {recipient_id} marked as Byzantine due to repeated errors")

    async def handle_message(self, reader, writer):
        while True:
            try:
                data = await reader.read(4)
                if not data:
                    break
                msg_len = int.from_bytes(data, "big")
                encrypted = await reader.read(msg_len)
                start_time = time.time()
                message = self.fernet.decrypt(encrypted).decode()
                message = json.loads(message)
                latency = time.time() - start_time
                if self.monitor:
                    self.monitor.log_metric(self.node_id, "latency", latency)
                await self.process_message(message)
                if self.monitor:
                    self.monitor.log_cpu_memory(self.node_id)
            except Exception as e:
                self.logger.error(f"Error processing message: {e}")
                break

    async def process_message(self, message: Dict):
        self.logger.debug(f"Processing {message['type']} from Node {message.get('sender_id', 'unknown')}")
        self.metrics["messages_received"].append((time.time(), 1))
        if self.monitor:
            self.monitor.log_metric(self.node_id, "messages_received", 1)

        if message["type"] == "prepare":
            if not await self.receive_vote("prepare", message["sender_id"], message["block"]["hash"], message["round"]):
                self.behavior_scores[message["sender_id"]] += 1
                if self.behavior_scores[message["sender_id"]] > 3:
                    self.byzantine_nodes.add(message["sender_id"])
                    self.logger.warning(f"Marked Node {message['sender_id']} as Byzantine due to invalid prepare votes")
        elif message["type"] == "precommit":
            if not await self.receive_vote("precommit", message["sender_id"], message["block"]["hash"], message["round"]):
                self.behavior_scores[message["sender_id"]] += 1
                if self.behavior_scores[message["sender_id"]] > 3:
                    self.byzantine_nodes.add(message["sender_id"])
                    self.logger.warning(f"Marked Node {message['sender_id']} as Byzantine due to invalid precommit votes")
        elif message["type"] == "commit":
            if not await self.receive_vote("commit", message["sender_id"], message["block"]["hash"], message["round"]):
                self.behavior_scores[message["sender_id"]] += 1
                if self.behavior_scores[message["sender_id"]] > 3:
                    self.byzantine_nodes.add(message["sender_id"])
                    self.logger.warning(f"Marked Node {message['sender_id']} as Byzantine due to invalid commit votes")
        elif message["type"] == "recovery_request":
            if (message["sender_id"], message["round"]) not in self.recovery_requests:
                self.recovery_requests.add((message["sender_id"], message["round"]))
                await self.send_recovery_data(message["sender_id"], message["round"])
        elif message["type"] == "recovery_response":
            await self.handle_recovery_data(message["data"], message["round"])
        elif message["type"] == "add_node":
            self.nodes.add(message["node_id"])
            self.logger.info(f"Added Node {message['node_id']} to the network")
        elif message["type"] == "remove_node":
            self.nodes.discard(message["node_id"])
            self.logger.info(f"Removed Node {message['node_id']} from the network")
        elif message["type"] == "shard_leader":
            self.shard_leaders[message["shard_id"]] = message["leader_id"]
        elif message["type"] == "shard_load":
            self.shard_load[message["shard_id"]] = message["load"]
            self.adjust_shards_if_needed()

    async def receive_vote(self, vote_type: str, node_id: int, block_hash: str, round: int) -> bool:
        if node_id in self.byzantine_nodes:
            self.logger.warning(f"Ignoring vote from Byzantine node {node_id}")
            return False
        if round != self.current_round:
            return False
        if block_hash != self.current_block.hash:
            return False
        if vote_type == "prepare":
            self.prepare_votes[node_id] = True
        elif vote_type == "precommit":
            self.precommit_votes[node_id] = True
        elif vote_type == "commit":
            self.commit_votes[node_id] = True
        self.logger.debug(f"Received {vote_type} vote from Node {node_id}")
        return True

    async def run_consensus_round(self, transactions: List[Dict]):
        self.current_round += 1
        self.shard_load[self.shard_id] += len(transactions)
        active_nodes = list(self.nodes - self.byzantine_nodes)
        if not active_nodes:
            self.logger.error("No active nodes left!")
            return
        self.current_leader = self.shard_leaders.get(self.shard_id, active_nodes[self.current_round % len(active_nodes)])
        self.logger.info(f"Running consensus round {self.current_round}")
        if self.node_id == self.current_leader:
            block = await self.propose_block(transactions)
            for node in active_nodes:
                if node != self.node_id:
                    await self.send_message(
                        {"type": "prepare", "block": {"hash": block.hash}, "round": self.current_round, "sender_id": self.node_id},
                        node
                    )

        if len(self.prepare_votes) > len(active_nodes) * 2 // 3:
            for node in active_nodes:
                if node != self.node_id:
                    await self.send_message(
                        {"type": "precommit", "block": {"hash": self.current_block.hash}, "round": self.current_round, "sender_id": self.node_id},
                        node
                    )

        if len(self.precommit_votes) > len(active_nodes) * 2 // 3:
            for node in active_nodes:
                if node != self.node_id:
                    await self.send_message(
                        {"type": "commit", "block": {"hash": self.current_block.hash}, "round": self.current_round, "sender_id": self.node_id},
                        node
                    )

        if len(self.commit_votes) > len(active_nodes) * 2 // 3:
            self.blockchain.append(self.current_block)
            if self.current_round % self.checkpoint_interval == 0:
                self.checkpoints[self.current_round] = self.current_block
                self.logger.info(f"Created checkpoint for round {self.current_round}: {self.current_block}")
            self.logger.info(f"Committed block: {self.current_block}")
            self.current_block = None
            self.prepare_votes = {}
            self.precommit_votes = {}
            self.commit_votes = {}

    def adjust_shards_if_needed(self):
        current_time = time.time()
        if current_time - self.last_shard_adjustment < self.shard_adjustment_interval:
            return
        avg_load = sum(self.shard_load.values()) / len(self.shard_load) if self.shard_load else 0
        if avg_load > 100:
            new_shard_id = max(self.shard_load.keys(), default=-1) + 1
            self.logger.info(f"Creating new shard {new_shard_id} due to high load")
            self.shard_leaders[new_shard_id] = random.choice(list(self.nodes - self.byzantine_nodes))
            for node in self.nodes:
                if node != self.node_id:
                    asyncio.create_task(self.send_message(
                        {"type": "shard_leader", "shard_id": new_shard_id, "leader_id": self.shard_leaders[new_shard_id], "sender_id": self.node_id},
                        node
                    ))
            self.last_shard_adjustment = current_time

    async def send_recovery_data(self, node_id: int, round: int):
        if round in self.checkpoints:
            await self.send_message(
                {"type": "recovery_response", "data": {"block": self.checkpoints[round].__dict__}, "round": round, "sender_id": self.node_id},
                node_id
            )
        elif round < len(self.blockchain):
            await self.send_message(
                {"type": "recovery_response", "data": {"block": self.blockchain[round].__dict__}, "round": round, "sender_id": self.node_id},
                node_id
            )

    async def handle_recovery_data(self, data: Dict, round: int):
        block_data = data["block"]
        block = Block(
            transactions=block_data["transactions"],
            previous_hash=block_data["previous_hash"],
            leader_id=block_data["leader_id"],
            round=block_data["round"],
            shard_id=block_data["shard_id"]
        )
        block.hash = block_data["hash"]
        if round == len(self.blockchain):
            self.blockchain.append(block)
            self.logger.info(f"Recovered block for round {round}: {block}")
        elif round < len(self.blockchain):
            self.blockchain[round] = block
            self.logger.info(f"Corrected block for round {round}: {block}")

    def make_byzantine(self):
        self.is_byzantine = True
        self.logger.warning(f"Node {self.node_id} is now Byzantine!")

    async def add_node(self, node_id: int):
        self.nodes.add(node_id)
        for node in self.nodes:
            if node != self.node_id:
                await self.send_message({"type": "add_node", "node_id": node_id, "sender_id": self.node_id}, node)

    async def remove_node(self, node_id: int):
        self.nodes.discard(node_id)
        for node in self.nodes:
            if node != self.node_id:
                await self.send_message({"type": "remove_node", "node_id": node_id, "sender_id": self.node_id}, node)

    async def auto_recover(self, target_round: int):
        self.logger.info(f"Starting auto-recovery to round {target_round}")
        for round in range(len(self.blockchain), target_round + 1):
            if round not in self.recovery_requests:
                recipient = random.choice(list(self.nodes - self.byzantine_nodes - {self.node_id}))
                await self.send_message(
                    {"type": "recovery_request", "round": round, "sender_id": self.node_id},
                    recipient
                )
                self.recovery_requests.add((self.node_id, round))
                await asyncio.sleep(0.5)

    def plot_metrics(self):
        if self.monitor:
            self.monitor.plot_metrics()
