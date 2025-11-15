import asyncio
import json
import random
import time
import psutil
from typing import List, Dict, Optional, Set, Tuple, Any
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from cryptography.fernet import Fernet
from block import Block
from logger import setup_logger
from distributed_ledger import DistributedLedger
from transaction import Transaction

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
        self.current_block: Optional[Dict[str, Any]] = None
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

        # Инициализация распределенного реестра
        self.ledger = DistributedLedger()
        self.ledger.balances[f"Node_{node_id}"] = 1000  # начальные балансы для узлов

    async def add_transaction(self, transaction_dict: Dict[str, Any]):
        transaction = Transaction(
            transaction_dict["from"],
            transaction_dict["to"],
            transaction_dict["amount"]
        )
        self.logger.info(f"Получена транзакция: {transaction}")
        self.ledger.add_transaction(transaction)
        self.logger.info(f"Транзакция добавлена в пул. Текущий размер пула: {len(self.ledger.pending_transactions)}")

    async def propose_block(self) -> Dict[str, Any]:
        pending_transactions = self.ledger.pending_transactions
        valid_transactions = []
        for tx in pending_transactions:
            if self.ledger.validate_transaction(tx):
                valid_transactions.append(tx)
            else:
                self.logger.warning(f"Транзакция отклонена: {tx}")

        block = self.ledger.create_block(valid_transactions, self.node_id, self.current_round)
        self.current_block = block
        self.logger.info(f"Предложен блок с {len(valid_transactions)} транзакциями: {block['hash']}")
        return block

    async def run_consensus_round(self):
        self.current_round += 1
        self.shard_load[self.shard_id] += 1
        active_nodes = list(self.nodes - self.byzantine_nodes)

        if not active_nodes:
            self.logger.error("Нет активных узлов!")
            return

        self.current_leader = self.shard_leaders.get(self.shard_id, active_nodes[self.current_round % len(active_nodes)])
        self.logger.info(f"Запуск раунда консенсуса {self.current_round}. Лидер: {self.current_leader}")

        if self.node_id == self.current_leader:
            block = await self.propose_block()
            for node in active_nodes:
                if node != self.node_id:
                    await self.send_message(
                        {"type": "prepare", "block": block, "round": self.current_round, "sender_id": self.node_id},
                        node
                    )

        if len(self.commit_votes) > len(active_nodes) * 2 // 3:
            self.ledger.add_block(self.current_block)
            self.logger.info(f"Блок зафиксирован: {self.current_block['hash']}")
            self.logger.info(f"Новые балансы: {self.ledger.balances}")
            self.current_block = None
            self.prepare_votes = {}
            self.precommit_votes = {}
            self.commit_votes = {}

    async def encrypt_message(self, message: Dict) -> bytes:
        self.logger.debug(f"Шифрование сообщения: {message}")
        return self.fernet.encrypt(json.dumps(message).encode())

    async def decrypt_message(self, encrypted: bytes) -> Dict:
        decrypted = self.fernet.decrypt(encrypted).decode()
        self.logger.debug(f"Расшифровано сообщение: {decrypted}")
        return json.loads(decrypted)

    async def send_message(self, message: Dict, recipient_id: int):
        if recipient_id in self.byzantine_nodes:
            self.logger.warning(f"Пропущен византийский узел {recipient_id}")
            return
        try:
            start_time = time.time()
            encrypted = await self.encrypt_message(message)
            self.message_batch.append((recipient_id, encrypted, start_time))
            current_time = time.time()
            if current_time - self.last_batch_time >= self.batch_interval:
                await self.flush_message_batch()
            self.logger.debug(f"Сообщение добавлено в пакет для узла {recipient_id}")
        except Exception as e:
            self.logger.error(f"Ошибка при добавлении сообщения в пакет для узла {recipient_id}: {e}")

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
                self.logger.debug(f"Отправлен пакет из {len(messages)} сообщений узлу {recipient_id}")
                self.metrics["messages_sent"].append((time.time(), len(messages)))
                if self.monitor:
                    self.monitor.log_metric(self.node_id, "messages_sent", len(messages))
                for _, start_time in messages:
                    latency = time.time() - start_time
                    self.latency_times[recipient_id].append(latency)
                    if self.monitor:
                        self.monitor.log_metric(self.node_id, "latency", latency)
            except Exception as e:
                self.logger.error(f"Не удалось отправить пакет узлу {recipient_id}: {e}")
                self.byzantine_nodes.add(recipient_id)
                self.behavior_scores[recipient_id] += 1
                if self.behavior_scores[recipient_id] > 3:
                    self.logger.warning(f"Узел {recipient_id} помечен как византийский из-за повторяющихся ошибок")

    async def handle_message(self, reader, writer):
        while True:
            try:
                data = await reader.read(4)
                if not data:
                    break
                msg_len = int.from_bytes(data, "big")
                encrypted = await reader.read(msg_len)
                start_time = time.time()
                message = await self.decrypt_message(encrypted)
                latency = time.time() - start_time
                if self.monitor:
                    self.monitor.log_metric(self.node_id, "latency", latency)
                await self.process_message(message)
                if self.monitor:
                    self.monitor.log_cpu_memory(self.node_id)
            except Exception as e:
                self.logger.error(f"Ошибка при обработке сообщения: {e}")
                break

    async def process_message(self, message: Dict):
        self.logger.debug(f"Обработка {message['type']} от узла {message.get('sender_id', 'неизвестно')}")
        self.metrics["messages_received"].append((time.time(), 1))
        if self.monitor:
            self.monitor.log_metric(self.node_id, "messages_received", 1)

        if message["type"] == "prepare":
            if not await self.receive_vote("prepare", message["sender_id"], message["block"]["hash"], message["round"]):
                self.behavior_scores[message["sender_id"]] += 1
                if self.behavior_scores[message["sender_id"]] > 3:
                    self.byzantine_nodes.add(message["sender_id"])
                    self.logger.warning(f"Узел {message['sender_id']} помечен как византийский из-за некорректных голосов prepare")
        elif message["type"] == "precommit":
            if not await self.receive_vote("precommit", message["sender_id"], message["block"]["hash"], message["round"]):
                self.behavior_scores[message["sender_id"]] += 1
                if self.behavior_scores[message["sender_id"]] > 3:
                    self.byzantine_nodes.add(message["sender_id"])
                    self.logger.warning(f"Узел {message['sender_id']} помечен как византийский из-за некорректных голосов precommit")
        elif message["type"] == "commit":
            if not await self.receive_vote("commit", message["sender_id"], message["block"]["hash"], message["round"]):
                self.behavior_scores[message["sender_id"]] += 1
                if self.behavior_scores[message["sender_id"]] > 3:
                    self.byzantine_nodes.add(message["sender_id"])
                    self.logger.warning(f"Узел {message['sender_id']} помечен как византийский из-за некорректных голосов commit")
        elif message["type"] == "recovery_request":
            if (message["sender_id"], message["round"]) not in self.recovery_requests:
                self.recovery_requests.add((message["sender_id"], message["round"]))
                await self.send_recovery_data(message["sender_id"], message["round"])
        elif message["type"] == "recovery_response":
            await self.handle_recovery_data(message["data"], message["round"])
        elif message["type"] == "add_node":
            self.nodes.add(message["node_id"])
            self.logger.info(f"Добавлен узел {message['node_id']} в сеть")
        elif message["type"] == "remove_node":
            self.nodes.discard(message["node_id"])
            self.logger.info(f"Удален узел {message['node_id']} из сети")
        elif message["type"] == "shard_leader":
            self.shard_leaders[message["shard_id"]] = message["leader_id"]
            self.logger.info(f"Назначен лидер {message['leader_id']} для шарда {message['shard_id']}")
        elif message["type"] == "shard_load":
            self.shard_load[message["shard_id"]] = message["load"]
            self.logger.info(f"Обновлена нагрузка для шарда {message['shard_id']}: {message['load']}")
            self.adjust_shards_if_needed()

    async def receive_vote(self, vote_type: str, node_id: int, block_hash: str, round: int) -> bool:
        if node_id in self.byzantine_nodes:
            self.logger.warning(f"Игнорируется голос от византийского узла {node_id}")
            return False
        if round != self.current_round:
            self.logger.debug(f"Голос от узла {node_id} для раунда {round} не соответствует текущему раунду {self.current_round}")
            return False
        if block_hash != self.current_block["hash"]:
            self.logger.debug(f"Голос от узла {node_id} для блока с хэшем {block_hash} не соответствует текущему блоку {self.current_block['hash']}")
            return False
        if vote_type == "prepare":
            self.prepare_votes[node_id] = True
        elif vote_type == "precommit":
            self.precommit_votes[node_id] = True
        elif vote_type == "commit":
            self.commit_votes[node_id] = True
        self.logger.debug(f"Получен {vote_type} голос от узла {node_id}")
        return True
