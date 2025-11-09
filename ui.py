import tkinter as tk
from tkinter import ttk, scrolledtext
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import threading
import queue
import time
import random
from collections import defaultdict
import logging

class HotStuffUI:
    def __init__(self, root, nodes):
        self.root = root
        self.nodes = nodes
        self.root.title("HotStuff Consensus Model")
        self.root.geometry("1200x800")

        self.ui_queue = queue.Queue()

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.general_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.general_tab, text="Общая информация")
        self.setup_general_tab()

        self.metrics_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.metrics_tab, text="Метрики")
        self.setup_metrics_tab()

        self.logs_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.logs_tab, text="Логи")
        self.setup_logs_tab()

        self.control_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.control_tab, text="Управление")
        self.setup_control_tab()

        self.running = True
        self.update_thread = threading.Thread(target=self.update_ui)
        self.update_thread.daemon = True
        self.update_thread.start()

        self.node_status = defaultdict(dict)
        self.metrics_data = defaultdict(lambda: defaultdict(list))

        self.ui_logger = logging.getLogger("ui_logger")
        self.ui_logger.setLevel(logging.DEBUG)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        self.ui_logger.addHandler(console_handler)

    def setup_general_tab(self):
        columns = ("ID", "Шард", "Статус", "Лидер", "Кол-во блоков", "Задержка (мс)")
        self.tree = ttk.Treeview(self.general_tab, columns=columns, show="headings", height=15)
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=100, anchor=tk.CENTER)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.shard_frame = ttk.LabelFrame(self.general_tab, text="Шарды")
        self.shard_frame.pack(fill=tk.X, padx=10, pady=10)
        self.shard_canvas = tk.Canvas(self.shard_frame, height=150, bg="white")
        self.shard_canvas.pack(fill=tk.X)

    def setup_metrics_tab(self):
        self.latency_fig = Figure(figsize=(5, 3), dpi=100)
        self.latency_plot = self.latency_fig.add_subplot(111)
        self.latency_plot.set_title("Задержка сети")
        self.latency_plot.set_xlabel("Время (с)")
        self.latency_plot.set_ylabel("Задержка (мс)")
        self.latency_canvas = FigureCanvasTkAgg(self.latency_fig, master=self.metrics_tab)
        self.latency_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.cpu_fig = Figure(figsize=(5, 3), dpi=100)
        self.cpu_plot = self.cpu_fig.add_subplot(111)
        self.cpu_plot.set_title("Использование CPU")
        self.cpu_plot.set_xlabel("Время (с)")
        self.cpu_plot.set_ylabel("CPU (%)")
        self.cpu_canvas = FigureCanvasTkAgg(self.cpu_fig, master=self.metrics_tab)
        self.cpu_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.memory_fig = Figure(figsize=(5, 3), dpi=100)
        self.memory_plot = self.memory_fig.add_subplot(111)
        self.memory_plot.set_title("Использование памяти")
        self.memory_plot.set_xlabel("Время (с)")
        self.memory_plot.set_ylabel("Память (МБ)")
        self.memory_canvas = FigureCanvasTkAgg(self.memory_fig, master=self.metrics_tab)
        self.memory_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    def setup_logs_tab(self):
        self.log_text = scrolledtext.ScrolledText(self.logs_tab, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def setup_control_tab(self):
        control_frame = ttk.Frame(self.control_tab)
        control_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(control_frame, text="Добавить узел:").grid(row=0, column=0, padx=5, pady=5)
        self.add_node_entry = ttk.Entry(control_frame, width=10)
        self.add_node_entry.grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(control_frame, text="Добавить", command=self.add_node).grid(row=0, column=2, padx=5, pady=5)

        ttk.Label(control_frame, text="Удалить узел:").grid(row=1, column=0, padx=5, pady=5)
        self.remove_node_entry = ttk.Entry(control_frame, width=10)
        self.remove_node_entry.grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(control_frame, text="Удалить", command=self.remove_node).grid(row=1, column=2, padx=5, pady=5)

        ttk.Label(control_frame, text="Интервал батчинга (с):").grid(row=2, column=0, padx=5, pady=5)
        self.batch_interval_entry = ttk.Entry(control_frame, width=10)
        self.batch_interval_entry.insert(0, "0.1")
        self.batch_interval_entry.grid(row=2, column=1, padx=5, pady=5)

    def add_node(self):
        try:
            node_id = int(self.add_node_entry.get())
            self.ui_queue.put(("add_node", node_id))
            self.ui_logger.info(f"Adding node {node_id}")
        except ValueError:
            self.ui_logger.error("Invalid node ID")

    def remove_node(self):
        try:
            node_id = int(self.remove_node_entry.get())
            self.ui_queue.put(("remove_node", node_id))
            self.ui_logger.info(f"Removing node {node_id}")
        except ValueError:
            self.ui_logger.error("Invalid node ID")

    def update_ui(self):
        while self.running:
            try:
                task = self.ui_queue.get(timeout=0.1)
                if task[0] == "add_node":
                    node_id = task[1]
                    if node_id not in self.nodes:
                        self.nodes.append(node_id)
                        self.ui_logger.info(f"Added node {node_id}")
                    self.update_general_tab()
                elif task[0] == "remove_node":
                    node_id = task[1]
                    if node_id in self.nodes:
                        self.nodes.remove(node_id)
                        self.ui_logger.info(f"Removed node {node_id}")
                    self.update_general_tab()
                elif task[0] == "log_message":
                    self.log_text.insert(tk.END, task[1] + "\n")
                    self.log_text.see(tk.END)
            except queue.Empty:
                pass

            self.update_metrics_tab()
            self.update_shard_visualization()
            self.generate_test_data()

            self.root.update_idletasks()
            self.root.update()
            time.sleep(0.1)

    def update_general_tab(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for node_id in self.nodes:
            status = "Активен" if random.random() > 0.1 else "Неактивен"
            is_leader = random.random() > 0.7
            block_count = random.randint(0, 100)
            latency = random.randint(10, 500)
            self.tree.insert("", tk.END, values=(node_id, node_id % 2, status, is_leader, block_count, latency))

    def update_metrics_tab(self):
        self.latency_plot.clear()
        for node_id in self.nodes:
            times = [i for i in range(len(self.metrics_data[node_id]["latency"]))]
            latencies = self.metrics_data[node_id]["latency"]
            self.latency_plot.plot(times, latencies, label=f"Node {node_id}")
        self.latency_plot.legend()
        self.latency_canvas.draw()

        self.cpu_plot.clear()
        for node_id in self.nodes:
            times = [i for i in range(len(self.metrics_data[node_id]["cpu"]))]
            cpu_usages = self.metrics_data[node_id]["cpu"]
            self.cpu_plot.plot(times, cpu_usages, label=f"Node {node_id}")
        self.cpu_plot.legend()
        self.cpu_canvas.draw()

        self.memory_plot.clear()
        for node_id in self.nodes:
            times = [i for i in range(len(self.metrics_data[node_id]["memory"]))]
            memory_usages = self.metrics_data[node_id]["memory"]
            self.memory_plot.plot(times, memory_usages, label=f"Node {node_id}")
        self.memory_plot.legend()
        self.memory_canvas.draw()

    def update_shard_visualization(self):
        self.shard_canvas.delete("all")
        shard_width = self.shard_canvas.winfo_width() // 2
        for i in range(2):
            self.shard_canvas.create_rectangle(i * shard_width, 10, (i + 1) * shard_width, 140, outline="black", fill="lightgray")
            self.shard_canvas.create_text(i * shard_width + shard_width // 2, 20, text=f"Шард {i}", font=("Arial", 12))
            nodes_in_shard = [node for node in self.nodes if node % 2 == i]
            for j, node in enumerate(nodes_in_shard):
                self.shard_canvas.create_oval(
                    i * shard_width + 20, 50 + j * 30,
                    i * shard_width + 40, 70 + j * 30,
                    fill="green" if random.random() > 0.1 else "red"
                )
                self.shard_canvas.create_text(
                    i * shard_width + 30, 60 + j * 30,
                    text=str(node), font=("Arial", 10)
                )

    def generate_test_data(self):
        for node_id in self.nodes:
            if "latency" not in self.metrics_data[node_id]:
                self.metrics_data[node_id]["latency"] = []
            if "cpu" not in self.metrics_data[node_id]:
                self.metrics_data[node_id]["cpu"] = []
            if "memory" not in self.metrics_data[node_id]:
                self.metrics_data[node_id]["memory"] = []

            self.metrics_data[node_id]["latency"].append(random.randint(10, 500))
            self.metrics_data[node_id]["cpu"].append(random.uniform(0, 100))
            self.metrics_data[node_id]["memory"].append(random.uniform(10, 500))

            if len(self.metrics_data[node_id]["latency"]) > 20:
                self.metrics_data[node_id]["latency"].pop(0)
                self.metrics_data[node_id]["cpu"].pop(0)
                self.metrics_data[node_id]["memory"].pop(0)

    def log_message(self, message):
        self.ui_queue.put(("log_message", message))
