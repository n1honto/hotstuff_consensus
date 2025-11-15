import tkinter as tk
from tkinter import ttk, scrolledtext
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import threading
import queue
import time
import random
import hashlib
import json
import networkx as nx
from collections import defaultdict, deque
import logging
from logging import handlers
from typing import Dict, List, Any, Optional, Tuple

class TextHandler(logging.Handler):
    def __init__(self, text_widget):
        logging.Handler.__init__(self)
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        def append():
            self.text_widget.insert(tk.END, msg + "\n")
            self.text_widget.see(tk.END)
        self.text_widget.after(100, append)

class ZoomableCanvas(tk.Canvas):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.scale = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.bind("<MouseWheel>", self.on_mousewheel)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonPress-1>", self.on_press)
        self.last_x = None
        self.last_y = None

    def on_mousewheel(self, event):
        if event.delta > 0:
            self.scale *= 1.1
        else:
            self.scale /= 1.1
        self.scale = max(0.1, min(self.scale, 5.0))
        self.update_view()

    def on_press(self, event):
        self.last_x = event.x
        self.last_y = event.y

    def on_drag(self, event):
        if self.last_x and self.last_y:
            dx = event.x - self.last_x
            dy = event.y - self.last_y
            self.offset_x += dx
            self.offset_y += dy
            self.update_view()
            self.last_x = event.x
            self.last_y = event.y

    def update_view(self):
        self.delete("all")
        if hasattr(self, 'draw_content'):
            self.draw_content()

class Transaction:
    def __init__(self, tx_id: str, sender: str, receiver: str, amount: float):
        self.tx_id = tx_id
        self.sender = sender
        self.receiver = receiver
        self.amount = amount
        self.timestamp = time.time()
        self.status = "created"  # created, in_pool, prepare, precommit, commit, in_blockchain
        self.current_round = 0
        self.votes = defaultdict(int)
        self.leader = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tx_id": self.tx_id,
            "sender": self.sender,
            "receiver": self.receiver,
            "amount": self.amount,
            "timestamp": self.timestamp,
            "status": self.status,
            "current_round": self.current_round,
            "votes": dict(self.votes)
        }

class HotStuffUI:
    def __init__(self, root: tk.Tk, nodes: List[int]):
        self.root = root
        self.nodes = nodes
        self.root.title("HotStuff Consensus - Transaction Lifecycle")
        self.root.geometry("1400x1000")

        self.ui_queue = queue.Queue()

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Вкладки
        self.consensus_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.consensus_tab, text="Консенсус HotStuff")
        self.setup_consensus_tab()

        self.ledger_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.ledger_tab, text="Распределенный реестр")
        self.setup_ledger_tab()

        self.network_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.network_tab, text="Сетевая топология")
        self.setup_network_tab()

        self.metrics_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.metrics_tab, text="Метрики")
        self.setup_metrics_tab()

        self.logs_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.logs_tab, text="Логи")
        self.setup_logs_tab()

        self.control_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.control_tab, text="Управление")
        self.setup_control_tab()

        # Данные для симуляции
        self.transactions: Dict[str, Transaction] = {}  # tx_id -> Transaction
        self.pending_transactions: deque = deque()  # Очередь транзакций для обработки
        self.current_round = 0
        self.current_leader = None
        self.consensus_phase = "idle"  # idle, prepare, precommit, commit
        self.votes: Dict[int, Dict[str, bool]] = defaultdict(dict)  # node_id -> {tx_id: voted}

        self.ledger_data: Dict[str, Any] = {
            "blocks": [],
            "balances": {"Alice": 1000, "Bob": 1000, "Charlie": 1000}
        }

        self.network_data: Dict[str, Any] = {
            "nodes": self.nodes,
            "edges": [],
            "transaction_distribution": defaultdict(list)  # node_id -> [tx_id]
        }

        self.metrics_data: Dict[str, Any] = {
            "latency": defaultdict(list),
            "cpu_usage": defaultdict(list),
            "memory_usage": defaultdict(list),
            "messages_sent": defaultdict(list),
            "messages_received": defaultdict(list),
            "time": []
        }

        self.running = True
        self.update_thread = threading.Thread(target=self.update_ui)
        self.update_thread.daemon = True
        self.update_thread.start()

        # Настройка логирования для UI
        self.ui_logger = logging.getLogger("ui_logger")
        self.ui_logger.setLevel(logging.DEBUG)

        # Создаем обработчик для вывода логов в текстовое поле
        self.text_handler = TextHandler(self.log_text)
        self.text_handler.setLevel(logging.DEBUG)
        self.text_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

        self.ui_logger.addHandler(self.text_handler)

        # Логируем старт приложения
        self.ui_logger.info("Запуск приложения HotStuff Consensus")

        # Запускаем автоматическую симуляцию
        self.start_simulation()

        # Таймер для обновления метрик
        self.root.after(1000, self.update_metrics)

    def setup_consensus_tab(self):
        container = tk.Frame(self.consensus_tab)
        container.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(container)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Виджет для отображения этапов консенсуса
        self.consensus_canvas = tk.Canvas(scrollable_frame, width=1200, height=800, bg="white")
        self.consensus_canvas.pack(fill=tk.BOTH, expand=True)

        # Информация о текущем раунде консенсуса
        self.consensus_info_frame = ttk.LabelFrame(scrollable_frame, text="Информация о консенсусе")
        self.consensus_info_frame.pack(fill=tk.X, pady=10)

        ttk.Label(self.consensus_info_frame, text="Раунд:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.round_label = ttk.Label(self.consensus_info_frame, text="0", width=10)
        self.round_label.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)

        ttk.Label(self.consensus_info_frame, text="Лидер:").grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        self.leader_label = ttk.Label(self.consensus_info_frame, text="-", width=10)
        self.leader_label.grid(row=0, column=3, padx=5, pady=5, sticky=tk.W)

        ttk.Label(self.consensus_info_frame, text="Фаза:").grid(row=0, column=4, padx=5, pady=5, sticky=tk.W)
        self.phase_label = ttk.Label(self.consensus_info_frame, text="idle", width=15)
        self.phase_label.grid(row=0, column=5, padx=5, pady=5, sticky=tk.W)

        ttk.Label(self.consensus_info_frame, text="Транзакций в обработке:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.tx_count_label = ttk.Label(self.consensus_info_frame, text="0", width=10)
        self.tx_count_label.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)

        # Легенда
        legend_frame = ttk.Frame(scrollable_frame)
        legend_frame.pack(fill=tk.X, pady=5)

        ttk.Label(legend_frame, text="Легенда:").pack(side=tk.LEFT, padx=5)
        ttk.Label(legend_frame, text="Создана", background="lightblue", width=10).pack(side=tk.LEFT, padx=5)
        ttk.Label(legend_frame, text="В пуле", background="lightgreen", width=10).pack(side=tk.LEFT, padx=5)
        ttk.Label(legend_frame, text="Prepare", background="yellow", width=10).pack(side=tk.LEFT, padx=5)
        ttk.Label(legend_frame, text="Pre-commit", background="orange", width=10).pack(side=tk.LEFT, padx=5)
        ttk.Label(legend_frame, text="Commit", background="pink", width=10).pack(side=tk.LEFT, padx=5)
        ttk.Label(legend_frame, text="В блокчейне", background="lightcoral", width=10).pack(side=tk.LEFT, padx=5)

    def setup_ledger_tab(self):
        container = tk.Frame(self.ledger_tab)
        container.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(container)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Виджет для отображения распределенного реестра
        self.ledger_canvas = tk.Canvas(scrollable_frame, width=1200, height=800, bg="white")
        self.ledger_canvas.pack(fill=tk.BOTH, expand=True)

        # Информация о реестре
        self.ledger_info_frame = ttk.LabelFrame(scrollable_frame, text="Информация о реестре")
        self.ledger_info_frame.pack(fill=tk.X, pady=10)

        ttk.Label(self.ledger_info_frame, text="Количество блоков:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.block_count_label = ttk.Label(self.ledger_info_frame, text="0", width=10)
        self.block_count_label.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)

        ttk.Label(self.ledger_info_frame, text="Транзакций в пуле:").grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        self.pool_count_label = ttk.Label(self.ledger_info_frame, text="0", width=10)
        self.pool_count_label.grid(row=0, column=3, padx=5, pady=5, sticky=tk.W)

        # Дерево для отображения блоков
        self.block_tree_frame = ttk.LabelFrame(scrollable_frame, text="Блоки")
        self.block_tree_frame.pack(fill=tk.BOTH, expand=True)

        block_columns = ("Индекс", "Хеш", "Время", "Кол-во транзакций", "Лидер", "Раунд")
        self.block_tree = ttk.Treeview(self.block_tree_frame, columns=block_columns, show="headings", height=10)
        for col in block_columns:
            self.block_tree.heading(col, text=col)
            self.block_tree.column(col, width=100, anchor=tk.CENTER)
        self.block_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Дерево для отображения транзакций
        self.tx_tree_frame = ttk.LabelFrame(scrollable_frame, text="Транзакции")
        self.tx_tree_frame.pack(fill=tk.BOTH, expand=True)

        tx_columns = ("ID", "Отправитель", "Получатель", "Сумма", "Время", "Статус", "Раунд")
        self.tx_tree = ttk.Treeview(self.tx_tree_frame, columns=tx_columns, show="headings", height=10)
        for col in tx_columns:
            self.tx_tree.heading(col, text=col)
            self.tx_tree.column(col, width=100, anchor=tk.CENTER)
        self.tx_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def setup_network_tab(self):
        container = tk.Frame(self.network_tab)
        container.pack(fill=tk.BOTH, expand=True)

        self.network_canvas = ZoomableCanvas(container, width=1200, height=800, bg="white")
        self.network_canvas.pack(fill=tk.BOTH, expand=True)
        self.network_canvas.draw_content = self.draw_network_content

        # Информация о сети
        self.network_info_frame = ttk.LabelFrame(container, text="Информация о сети")
        self.network_info_frame.pack(fill=tk.X, pady=10)

        ttk.Label(self.network_info_frame, text="Количество узлов:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.node_count_label = ttk.Label(self.network_info_frame, text=str(len(self.nodes)), width=10)
        self.node_count_label.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)

        ttk.Label(self.network_info_frame, text="Активные узлы:").grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        self.active_nodes_label = ttk.Label(self.network_info_frame, text=str(len(self.nodes)), width=10)
        self.active_nodes_label.grid(row=0, column=3, padx=5, pady=5, sticky=tk.W)

        # Легенда для сети
        legend_frame = ttk.Frame(container)
        legend_frame.pack(fill=tk.X, pady=5)

        ttk.Label(legend_frame, text="Легенда:").pack(side=tk.LEFT, padx=5)
        ttk.Label(legend_frame, text="Узел", background="lightblue", width=10).pack(side=tk.LEFT, padx=5)
        ttk.Label(legend_frame, text="Лидер", background="lightgreen", width=10).pack(side=tk.LEFT, padx=5)
        ttk.Label(legend_frame, text="Транзакция", background="red", width=10).pack(side=tk.LEFT, padx=5)

    def setup_metrics_tab(self):
        container = tk.Frame(self.metrics_tab)
        container.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(container)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # График задержки сети
        self.latency_fig = Figure(figsize=(10, 4), dpi=100)
        self.latency_plot = self.latency_fig.add_subplot(111)
        self.latency_plot.set_title("Задержка сети (мс)", fontsize=12, fontweight='bold', pad=20)
        self.latency_plot.set_xlabel("Время (с)", fontsize=10, labelpad=15)
        self.latency_plot.set_ylabel("Задержка (мс)", fontsize=10, labelpad=15)
        self.latency_plot.grid(True)
        self.latency_canvas = FigureCanvasTkAgg(self.latency_fig, master=scrollable_frame)
        self.latency_toolbar = NavigationToolbar2Tk(self.latency_canvas, scrollable_frame)
        self.latency_toolbar.update()
        self.latency_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=20)

        # График использования CPU
        self.cpu_fig = Figure(figsize=(10, 4), dpi=100)
        self.cpu_plot = self.cpu_fig.add_subplot(111)
        self.cpu_plot.set_title("Использование CPU (%)", fontsize=12, fontweight='bold', pad=20)
        self.cpu_plot.set_xlabel("Время (с)", fontsize=10, labelpad=15)
        self.cpu_plot.set_ylabel("Использование CPU (%)", fontsize=10, labelpad=15)
        self.cpu_plot.grid(True)
        self.cpu_canvas = FigureCanvasTkAgg(self.cpu_fig, master=scrollable_frame)
        self.cpu_toolbar = NavigationToolbar2Tk(self.cpu_canvas, scrollable_frame)
        self.cpu_toolbar.update()
        self.cpu_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=20)

    def setup_logs_tab(self):
        container = tk.Frame(self.logs_tab)
        container.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(container)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.log_text = scrolledtext.ScrolledText(scrollable_frame, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def setup_control_tab(self):
        control_frame = ttk.Frame(self.control_tab)
        control_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(control_frame, text="Отправитель:").grid(row=0, column=0, padx=5, pady=5)
        self.from_entry = ttk.Entry(control_frame, width=15)
        self.from_entry.grid(row=0, column=1, padx=5, pady=5)
        self.from_entry.insert(0, "Alice")

        ttk.Label(control_frame, text="Получатель:").grid(row=0, column=2, padx=5, pady=5)
        self.to_entry = ttk.Entry(control_frame, width=15)
        self.to_entry.grid(row=0, column=3, padx=5, pady=5)
        self.to_entry.insert(0, "Bob")

        ttk.Label(control_frame, text="Сумма:").grid(row=0, column=4, padx=5, pady=5)
        self.amount_entry = ttk.Entry(control_frame, width=10)
        self.amount_entry.grid(row=0, column=5, padx=5, pady=5)
        self.amount_entry.insert(0, "100")

        ttk.Button(control_frame, text="Отправить транзакцию", command=self.send_transaction).grid(row=0, column=6, padx=5, pady=5)

        # Поля для отображения балансов
        ttk.Label(control_frame, text="Баланс Alice:").grid(row=1, column=0, padx=5, pady=5)
        self.alice_balance_label = ttk.Label(control_frame, text="1000", width=10)
        self.alice_balance_label.grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(control_frame, text="Баланс Bob:").grid(row=1, column=2, padx=5, pady=5)
        self.bob_balance_label = ttk.Label(control_frame, text="1000", width=10)
        self.bob_balance_label.grid(row=1, column=3, padx=5, pady=5)

        ttk.Label(control_frame, text="Баланс Charlie:").grid(row=1, column=4, padx=5, pady=5)
        self.charlie_balance_label = ttk.Label(control_frame, text="1000", width=10)
        self.charlie_balance_label.grid(row=1, column=5, padx=5, pady=5)

        ttk.Button(control_frame, text="Обновить балансы", command=self.update_balances).grid(row=1, column=6, padx=5, pady=5)

    def start_simulation(self):
        """Запускает автоматическую симуляцию консенсуса"""
        self.simulate_transaction_creation()
        self.root.after(1000, self.process_transactions)  # Начинаем обработку транзакций

    def simulate_transaction_creation(self):
        """Симулирует создание транзакции"""
        sender = random.choice(["Alice", "Bob", "Charlie"])
        receiver = random.choice([u for u in ["Alice", "Bob", "Charlie"] if u != sender])
        amount = random.randint(10, 100)

        tx_id = hashlib.sha256(f"{sender}{receiver}{amount}{time.time()}".encode()).hexdigest()[:16]
        transaction = Transaction(tx_id, sender, receiver, amount)

        self.transactions[tx_id] = transaction
        self.pending_transactions.append(tx_id)
        self.network_data["transaction_distribution"][random.choice(self.nodes)].append(tx_id)

        self.ui_logger.info(f"Создана транзакция {tx_id}: {sender}->{receiver}:{amount}")
        self.update_consensus_visualization()
        self.update_ledger_visualization()
        self.update_network_visualization()

        # Планируем следующую транзакцию
        self.root.after(random.randint(2000, 5000), self.simulate_transaction_creation)

    def process_transactions(self):
        """Обрабатывает транзакции в очереди"""
        if not self.pending_transactions:
            self.root.after(1000, self.process_transactions)
            return

        # Начинаем новый раунд консенсуса
        self.current_round += 1
        self.current_leader = random.choice(self.nodes)
        self.consensus_phase = "prepare"

        self.round_label.config(text=str(self.current_round))
        self.leader_label.config(text=str(self.current_leader))
        self.phase_label.config(text="prepare")
        self.tx_count_label.config(text=str(len(self.pending_transactions)))

        self.ui_logger.info(f"Начат раунд {self.current_round} с лидером {self.current_leader}")

        # Обрабатываем первую транзакцию в очереди
        self.process_transaction()

    def process_transaction(self):
        """Обрабатывает одну транзакцию"""
        if not self.pending_transactions:
            self.consensus_phase = "idle"
            self.phase_label.config(text="idle")
            self.root.after(1000, self.process_transactions)
            return

        tx_id = self.pending_transactions[0]
        transaction = self.transactions[tx_id]

        # Устанавливаем текущий раунд и лидера для транзакции
        transaction.current_round = self.current_round
        transaction.leader = self.current_leader

        # Фаза Prepare
        self.ui_logger.info(f"Транзакция {tx_id}: Фаза Prepare")
        transaction.status = "prepare"
        self.update_consensus_visualization()
        self.update_tx_tree()

        # Симулируем голоса узлов
        self.root.after(500, lambda: self.vote_prepare(tx_id))

    def vote_prepare(self, tx_id: str):
        """Симулирует голосование на фазе Prepare"""
        transaction = self.transactions[tx_id]

        # Симулируем голоса узлов
        for node in self.nodes:
            if random.random() > 0.2:  # 80% вероятность голосования
                transaction.votes[node] = True

        total_votes = sum(1 for vote in transaction.votes.values() if vote)
        self.ui_logger.info(f"Транзакция {tx_id}: Получено {total_votes}/{len(self.nodes)} голосов Prepare")

        if total_votes > len(self.nodes) * 2 / 3:
            # Переходим к фазе Pre-commit
            self.ui_logger.info(f"Транзакция {tx_id}: Фаза Pre-commit")
            transaction.status = "precommit"
            self.update_consensus_visualization()
            self.update_tx_tree()
            self.root.after(500, lambda: self.vote_precommit(tx_id))
        else:
            # Транзакция не набрала достаточно голосов, возвращаем в пул
            self.ui_logger.warning(f"Транзакция {tx_id}: Недостаточно голосов Prepare")
            transaction.status = "in_pool"
            self.update_consensus_visualization()
            self.update_tx_tree()
            self.root.after(500, self.process_transaction)

    def vote_precommit(self, tx_id: str):
        """Симулирует голосование на фазе Pre-commit"""
        transaction = self.transactions[tx_id]

        # Симулируем голоса узлов
        for node in self.nodes:
            if random.random() > 0.2:  # 80% вероятность голосования
                transaction.votes[node] = True

        total_votes = sum(1 for vote in transaction.votes.values() if vote)
        self.ui_logger.info(f"Транзакция {tx_id}: Получено {total_votes}/{len(self.nodes)} голосов Pre-commit")

        if total_votes > len(self.nodes) * 2 / 3:
            # Переходим к фазе Commit
            self.ui_logger.info(f"Транзакция {tx_id}: Фаза Commit")
            transaction.status = "commit"
            self.update_consensus_visualization()
            self.update_tx_tree()
            self.root.after(500, lambda: self.vote_commit(tx_id))
        else:
            # Транзакция не набрала достаточно голосов, возвращаем в пул
            self.ui_logger.warning(f"Транзакция {tx_id}: Недостаточно голосов Pre-commit")
            transaction.status = "in_pool"
            self.update_consensus_visualization()
            self.update_tx_tree()
            self.root.after(500, self.process_transaction)

    def vote_commit(self, tx_id: str):
        """Симулирует голосование на фазе Commit"""
        transaction = self.transactions[tx_id]

        # Симулируем голоса узлов
        for node in self.nodes:
            if random.random() > 0.2:  # 80% вероятность голосования
                transaction.votes[node] = True

        total_votes = sum(1 for vote in transaction.votes.values() if vote)
        self.ui_logger.info(f"Транзакция {tx_id}: Получено {total_votes}/{len(self.nodes)} голосов Commit")

        if total_votes > len(self.nodes) * 2 / 3:
            # Транзакция подтверждена, добавляем в блокчейн
            self.ui_logger.info(f"Транзакция {tx_id}: Подтверждена и добавлена в блокчейн")
            transaction.status = "in_blockchain"

            # Создаем блок с этой транзакцией
            block = {
                "index": len(self.ledger_data["blocks"]) + 1,
                "timestamp": time.time(),
                "transactions": [transaction.to_dict()],
                "leader_id": transaction.leader,
                "round": transaction.current_round,
                "previous_hash": self.ledger_data["blocks"][-1]["hash"] if self.ledger_data["blocks"] else "0"
            }
            block["hash"] = hashlib.sha256(json.dumps(block, sort_keys=True).encode()).hexdigest()

            self.ledger_data["blocks"].append(block)

            # Применяем транзакцию к балансам
            self.ledger_data["balances"][transaction.sender] -= transaction.amount
            self.ledger_data["balances"][transaction.receiver] += transaction.amount

            # Удаляем транзакцию из очереди
            self.pending_transactions.popleft()

            self.update_consensus_visualization()
            self.update_ledger_visualization()
            self.update_network_visualization()
            self.update_balances()
            self.update_tx_tree()

            # Переходим к обработке следующей транзакции
            self.root.after(500, self.process_transaction)
        else:
            # Транзакция не набрала достаточно голосов, возвращаем в пул
            self.ui_logger.warning(f"Транзакция {tx_id}: Недостаточно голосов Commit")
            transaction.status = "in_pool"
            self.update_consensus_visualization()
            self.update_tx_tree()
            self.root.after(500, self.process_transaction)

    def update_consensus_visualization(self):
        """Обновляет визуализацию консенсуса"""
        self.consensus_canvas.delete("all")

        # Отрисовка этапов консенсуса
        phases = ["Создана", "В пуле", "Prepare", "Pre-commit", "Commit", "В блокчейне"]
        phase_colors = ["lightblue", "lightgreen", "yellow", "orange", "pink", "lightcoral"]

        for i, phase in enumerate(phases):
            x = 100 + i * 180
            y = 200
            self.consensus_canvas.create_rectangle(x, y, x + 150, y + 100, fill="gray", outline="black")
            self.consensus_canvas.create_text(x + 75, y + 50, text=phase, font=("Arial", 10, "bold"))

            # Соединяем этапы
            if i > 0:
                self.consensus_canvas.create_line(x, y + 50, x - 70, y + 50, arrow=tk.LAST)

        # Отрисовка транзакций на соответствующих этапах
        for tx_id, transaction in self.transactions.items():
            if transaction.status == "created":
                x, y = 155, 50 + list(self.transactions.keys()).index(tx_id) * 40
            elif transaction.status == "in_pool":
                x, y = 335, 50 + list(self.transactions.keys()).index(tx_id) * 40
            elif transaction.status == "prepare":
                x, y = 515, 50 + list(self.transactions.keys()).index(tx_id) * 40
            elif transaction.status == "precommit":
                x, y = 695, 50 + list(self.transactions.keys()).index(tx_id) * 40
            elif transaction.status == "commit":
                x, y = 875, 50 + list(self.transactions.keys()).index(tx_id) * 40
            elif transaction.status == "in_blockchain":
                x, y = 1055, 50 + list(self.transactions.keys()).index(tx_id) * 40
            else:
                continue

            # Определяем цвет в зависимости от статуса
            if transaction.status == "created":
                color = "lightblue"
            elif transaction.status == "in_pool":
                color = "lightgreen"
            elif transaction.status == "prepare":
                color = "yellow"
            elif transaction.status == "precommit":
                color = "orange"
            elif transaction.status == "commit":
                color = "pink"
            elif transaction.status == "in_blockchain":
                color = "lightcoral"

            self.consensus_canvas.create_rectangle(x, y, x + 140, y + 30, fill=color, outline="black")
            self.consensus_canvas.create_text(x + 70, y + 15,
                text=f"{transaction.sender}->{transaction.receiver}:{transaction.amount}\n{tx_id[:8]}...",
                font=("Arial", 8))

            # Соединяем транзакцию с соответствующим этапом
            if transaction.status == "created":
                target_x, target_y = 155, 200
            elif transaction.status == "in_pool":
                target_x, target_y = 335, 200
            elif transaction.status == "prepare":
                target_x, target_y = 515, 200
            elif transaction.status == "precommit":
                target_x, target_y = 695, 200
            elif transaction.status == "commit":
                target_x, target_y = 875, 200
            elif transaction.status == "in_blockchain":
                target_x, target_y = 1055, 200

            self.consensus_canvas.create_line(x + 70, y + 15, target_x, target_y, arrow=tk.LAST)

    def update_ledger_visualization(self):
        """Обновляет визуализацию распределенного реестра"""
        self.ledger_canvas.delete("all")

        # Отрисовка блокчейна
        for i, block in enumerate(self.ledger_data["blocks"]):
            x = 50 + i * 200
            y = 100
            self.ledger_canvas.create_rectangle(x, y, x + 150, y + 100, fill="lightgreen", outline="black")
            self.ledger_canvas.create_text(x + 75, y + 20, text=f"Block {block['index']}", font=("Arial", 10, "bold"))
            self.ledger_canvas.create_text(x + 75, y + 50, text=f"Hash: {block['hash'][:10]}...", font=("Arial", 8))
            self.ledger_canvas.create_text(x + 75, y + 80, text=f"Tx: {len(block['transactions'])}", font=("Arial", 8))

            # Соединяем блоки
            if i > 0:
                self.ledger_canvas.create_line(x, y + 50, x - 50, y + 50, arrow=tk.LAST)

        # Отрисовка транзакций в пуле
        for i, tx_id in enumerate(self.pending_transactions):
            transaction = self.transactions[tx_id]
            x = 50
            y = 250 + i * 40
            self.ledger_canvas.create_rectangle(x, y, x + 300, y + 30, fill="lightblue", outline="black")
            self.ledger_canvas.create_text(x + 150, y + 15,
                text=f"{transaction.sender}->{transaction.receiver}:{transaction.amount}\n{tx_id[:8]}...",
                font=("Arial", 8))

        # Обновление информации о реестре
        self.block_count_label.config(text=str(len(self.ledger_data["blocks"])))
        self.pool_count_label.config(text=str(len(self.pending_transactions)))

        # Обновление деревьев
        self.update_block_tree()
        self.update_tx_tree()

    def draw_network_content(self):
        """Отрисовка сетевой топологии с учетом масштаба и смещения"""
        self.network_canvas.delete("all")

        # Создаем граф сети
        G = nx.Graph()

        # Добавляем узлы
        for node in self.nodes:
            G.add_node(node)

        # Добавляем связи между узлами
        for i in range(len(self.nodes)):
            for j in range(i + 1, len(self.nodes)):
                G.add_edge(self.nodes[i], self.nodes[j])

        # Отрисовка графа
        pos = nx.spring_layout(G)
        node_positions = {}

        # Масштабируем и центрируем граф
        min_x = min(p[0] for p in pos.values())
        max_x = max(p[0] for p in pos.values())
        min_y = min(p[1] for p in pos.values())
        max_y = max(p[1] for p in pos.values())

        scale = min(1000 / (max_x - min_x), 500 / (max_y - min_y)) * self.network_canvas.scale
        offset_x = 600 - (min_x + max_x) * scale / 2 + self.network_canvas.offset_x
        offset_y = 300 - (min_y + max_y) * scale / 2 + self.network_canvas.offset_y

        for node, (x, y) in pos.items():
            node_positions[node] = (x * scale + offset_x, y * scale + offset_y)

        for node in G.nodes():
            x, y = node_positions[node]
            color = "lightgreen" if node == self.current_leader else "lightblue"
            self.network_canvas.create_oval(x - 20, y - 20, x + 20, y + 20, fill=color, outline="black")
            self.network_canvas.create_text(x, y, text=str(node), font=("Arial", 10, "bold"))

            # Отрисовка транзакций на узлах
            node_transactions = self.network_data["transaction_distribution"].get(node, [])
            for i, tx_id in enumerate(node_transactions[:3]):  # Показываем первые 3 транзакции
                transaction = self.transactions.get(tx_id)
                if transaction:
                    status_color = {
                        "created": "blue",
                        "in_pool": "green",
                        "prepare": "orange",
                        "precommit": "red",
                        "commit": "purple",
                        "in_blockchain": "gray"
                    }.get(transaction.status, "black")

                    self.network_canvas.create_text(x, y + 30 + i * 15,
                        text=f"{tx_id[:6]} ({transaction.status[:3]})",
                        font=("Arial", 8), fill=status_color)

        for edge in G.edges():
            x1, y1 = node_positions[edge[0]]
            x2, y2 = node_positions[edge[1]]
            self.network_canvas.create_line(x1, y1, x2, y2, fill="gray")

        # Выделяем лидера
        if self.current_leader is not None:
            x, y = node_positions[self.current_leader]
            self.network_canvas.create_oval(x - 25, y - 25, x + 25, y + 25, fill="lightgreen", outline="black")
            self.network_canvas.create_text(x, y, text=f"L{self.current_leader}", font=("Arial", 10, "bold"))

    def update_network_visualization(self):
        """Обновляет визуализацию сетевой топологии"""
        self.network_canvas.update_view()

    def update_block_tree(self):
        """Обновляет дерево блоков"""
        for item in self.block_tree.get_children():
            self.block_tree.delete(item)

        for block in self.ledger_data["blocks"]:
            self.block_tree.insert("", tk.END, values=(
                block["index"],
                block["hash"][:10] + "...",
                time.strftime("%H:%M:%S", time.localtime(block["timestamp"])),
                len(block["transactions"]),
                block["leader_id"],
                block["round"]
            ))

    def update_tx_tree(self):
        """Обновляет дерево транзакций"""
        for item in self.tx_tree.get_children():
            self.tx_tree.delete(item)

        for tx_id, transaction in self.transactions.items():
            status_text = {
                "created": "Создана",
                "in_pool": "В пуле",
                "prepare": "Prepare",
                "precommit": "Pre-commit",
                "commit": "Commit",
                "in_blockchain": "В блокчейне"
            }.get(transaction.status, "Неизвестно")

            self.tx_tree.insert("", tk.END, values=(
                tx_id[:8] + "...",
                transaction.sender,
                transaction.receiver,
                transaction.amount,
                time.strftime("%H:%M:%S", time.localtime(transaction.timestamp)),
                status_text,
                transaction.current_round if transaction.current_round > 0 else "-"
            ))

    def send_transaction(self):
        """Отправляет транзакцию в сеть"""
        try:
            from_user = self.from_entry.get()
            to_user = self.to_entry.get()
            amount = float(self.amount_entry.get())

            if from_user == to_user:
                self.ui_logger.error("Отправитель и получатель не могут быть одинаковыми")
                return

            if from_user not in self.ledger_data["balances"] or to_user not in self.ledger_data["balances"]:
                self.ui_logger.error("Некорректные пользователи")
                return

            if self.ledger_data["balances"][from_user] < amount:
                self.ui_logger.error("Недостаточно средств")
                return

            tx_id = hashlib.sha256(f"{from_user}{to_user}{amount}{time.time()}".encode()).hexdigest()[:16]
            transaction = Transaction(tx_id, from_user, to_user, amount)

            self.transactions[tx_id] = transaction
            self.pending_transactions.append(tx_id)
            self.network_data["transaction_distribution"][random.choice(self.nodes)].append(tx_id)

            self.ui_logger.info(f"Отправлена транзакция {tx_id}: {from_user}->{to_user}:{amount}")
            self.update_consensus_visualization()
            self.update_ledger_visualization()
            self.update_network_visualization()
            self.update_tx_tree()
        except ValueError:
            self.ui_logger.error("Некорректные данные транзакции")

    def update_balances(self):
        """Обновляет отображение балансов"""
        self.alice_balance_label.config(text=f"{self.ledger_data['balances'].get('Alice', 0):.2f}")
        self.bob_balance_label.config(text=f"{self.ledger_data['balances'].get('Bob', 0):.2f}")
        self.charlie_balance_label.config(text=f"{self.ledger_data['balances'].get('Charlie', 0):.2f}")

    def update_metrics(self):
        """Обновляет метрики"""
        current_time = len(self.metrics_data["time"])

        # Симулируем метрики
        for node in self.nodes:
            # Задержка сети
            self.metrics_data["latency"][node].append(random.uniform(10, 100))

            # Использование CPU
            self.metrics_data["cpu_usage"][node].append(random.uniform(5, 30))

            # Использование памяти
            self.metrics_data["memory_usage"][node].append(random.uniform(50, 200))

        self.metrics_data["time"].append(current_time)

        # Обновляем графики
        self.update_latency_plot()
        self.update_cpu_plot()

        # Планируем следующее обновление
        self.root.after(1000, self.update_metrics)

    def update_latency_plot(self):
        """Обновляет график задержки сети"""
        self.latency_plot.clear()

        for node in self.nodes:
            times = list(range(len(self.metrics_data["latency"][node])))
            latencies = self.metrics_data["latency"][node]
            self.latency_plot.plot(times, latencies, label=f"Node {node}")

        self.latency_plot.legend(loc='upper right')
        self.latency_plot.set_title("Задержка сети (мс)", fontsize=12, fontweight='bold', pad=20)
        self.latency_plot.set_xlabel("Время (с)", fontsize=10, labelpad=15)
        self.latency_plot.set_ylabel("Задержка (мс)", fontsize=10, labelpad=15)
        self.latency_plot.grid(True)
        self.latency_canvas.draw()

    def update_cpu_plot(self):
        """Обновляет график использования CPU"""
        self.cpu_plot.clear()

        for node in self.nodes:
            times = list(range(len(self.metrics_data["cpu_usage"][node])))
            cpu_usages = self.metrics_data["cpu_usage"][node]
            self.cpu_plot.plot(times, cpu_usages, label=f"Node {node}")

        self.cpu_plot.legend(loc='upper right')
        self.cpu_plot.set_title("Использование CPU (%)", fontsize=12, fontweight='bold', pad=20)
        self.cpu_plot.set_xlabel("Время (с)", fontsize=10, labelpad=15)
        self.cpu_plot.set_ylabel("Использование CPU (%)", fontsize=10, labelpad=15)
        self.cpu_plot.grid(True)
        self.cpu_canvas.draw()

    def update_ui(self):
        """Основной цикл обновления UI"""
        while self.running:
            try:
                task = self.ui_queue.get(timeout=0.1)
                # Обработка задач из очереди
            except queue.Empty:
                pass

            self.root.update_idletasks()
            self.root.update()
            time.sleep(0.1)

if __name__ == "__main__":
    root = tk.Tk()
    app = HotStuffUI(root, [0, 1, 2, 3, 4])
    root.mainloop()
