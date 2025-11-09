import tkinter as tk
from tkinter import ttk, scrolledtext
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import threading
import queue
import time
import random
from collections import defaultdict
import logging
from logging import handlers

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
        self.time_counter = 0
        self.max_data_points = 100  # Максимальное количество точек на графиках

        # Настройка логирования для UI
        self.ui_logger = logging.getLogger("ui_logger")
        self.ui_logger.setLevel(logging.DEBUG)

        # Создаем обработчик для вывода логов в текстовое поле
        self.text_handler = TextHandler(self.log_text)
        self.text_handler.setLevel(logging.DEBUG)
        self.text_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

        self.ui_logger.addHandler(self.text_handler)

        # Заполняем таблицу общей информации начальными данными
        self.update_general_tab()

        # Логируем старт приложения
        self.ui_logger.info("Запуск приложения HotStuff Consensus Model")

        # Таймер для генерации логов
        self.root.after(100, self.generate_logs)

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
        # Создаем контейнер с прокруткой
        self.metrics_container = tk.Frame(self.metrics_tab)
        self.metrics_container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self.metrics_container)
        self.scrollbar = ttk.Scrollbar(self.metrics_container, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # График задержки сети
        self.latency_fig = Figure(figsize=(10, 4), dpi=100)  # Увеличили длину графика
        self.latency_plot = self.latency_fig.add_subplot(111)
        self.latency_plot.set_title("Задержка сети (мс)", fontsize=12, fontweight='bold', pad=20)
        self.latency_plot.set_xlabel("Время (условные единицы)", fontsize=10, labelpad=15)  # Изменили подпись оси X
        self.latency_plot.set_ylabel("Задержка (мс)", fontsize=10, labelpad=15)
        self.latency_plot.grid(True)
        self.latency_canvas = FigureCanvasTkAgg(self.latency_fig, master=self.scrollable_frame)
        self.latency_toolbar = NavigationToolbar2Tk(self.latency_canvas, self.scrollable_frame)
        self.latency_toolbar.update()
        self.latency_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=20)

        # График использования CPU
        self.cpu_fig = Figure(figsize=(10, 4), dpi=100)  # Увеличили длину графика
        self.cpu_plot = self.cpu_fig.add_subplot(111)
        self.cpu_plot.set_title("Использование CPU (%)", fontsize=12, fontweight='bold', pad=20)
        self.cpu_plot.set_xlabel("Время (условные единицы)", fontsize=10, labelpad=15)  # Изменили подпись оси X
        self.cpu_plot.set_ylabel("Использование CPU (%)", fontsize=10, labelpad=15)
        self.cpu_plot.grid(True)
        self.cpu_canvas = FigureCanvasTkAgg(self.cpu_fig, master=self.scrollable_frame)
        self.cpu_toolbar = NavigationToolbar2Tk(self.cpu_canvas, self.scrollable_frame)
        self.cpu_toolbar.update()
        self.cpu_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=20)

        # График использования памяти
        self.memory_fig = Figure(figsize=(10, 4), dpi=100)  # Увеличили длину графика
        self.memory_plot = self.memory_fig.add_subplot(111)
        self.memory_plot.set_title("Использование памяти (МБ)", fontsize=12, fontweight='bold', pad=20)
        self.memory_plot.set_xlabel("Время (условные единицы)", fontsize=10, labelpad=15)  # Изменили подпись оси X
        self.memory_plot.set_ylabel("Использование памяти (МБ)", fontsize=10, labelpad=15)
        self.memory_plot.grid(True)
        self.memory_canvas = FigureCanvasTkAgg(self.memory_fig, master=self.scrollable_frame)
        self.memory_toolbar = NavigationToolbar2Tk(self.memory_canvas, self.scrollable_frame)
        self.memory_toolbar.update()
        self.memory_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=20)

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
            self.ui_logger.info(f"Добавлен узел {node_id}")
        except ValueError:
            self.ui_logger.error("Некорректный ID узла")

    def remove_node(self):
        try:
            node_id = int(self.remove_node_entry.get())
            self.ui_queue.put(("remove_node", node_id))
            self.ui_logger.info(f"Удален узел {node_id}")
        except ValueError:
            self.ui_logger.error("Некорректный ID узла")

    def update_ui(self):
        while self.running:
            try:
                task = self.ui_queue.get(timeout=0.1)
                if task[0] == "add_node":
                    node_id = task[1]
                    if node_id not in self.nodes:
                        self.nodes.append(node_id)
                        self.ui_logger.info(f"Добавлен узел {node_id}")
                    self.update_general_tab()
                elif task[0] == "remove_node":
                    node_id = task[1]
                    if node_id in self.nodes:
                        self.nodes.remove(node_id)
                        self.ui_logger.info(f"Удален узел {node_id}")
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

        # Заполняем таблицу данными о узлах
        for node_id in self.nodes:
            status = "Активен" if random.random() > 0.1 else "Неактивен"
            is_leader = random.random() > 0.7
            block_count = random.randint(0, 100)
            latency = random.randint(10, 500)
            shard_id = node_id % 2
            self.tree.insert("", tk.END, values=(node_id, shard_id, status, is_leader, block_count, latency))

    def update_metrics_tab(self):
        self.time_counter += 1

        # Обновление графика задержки
        self.latency_plot.clear()
        for node_id in self.nodes:
            times = list(range(len(self.metrics_data[node_id]["latency"])))
            latencies = self.metrics_data[node_id]["latency"]
            self.latency_plot.plot(times, latencies, label=f"Узел {node_id}")
        self.latency_plot.legend(loc='upper right')
        self.latency_plot.set_title("Задержка сети (мс)", fontsize=12, fontweight='bold', pad=20)
        self.latency_plot.set_xlabel("Время (условные единицы)", fontsize=10, labelpad=15)
        self.latency_plot.set_ylabel("Задержка (мс)", fontsize=10, labelpad=15)
        self.latency_plot.grid(True)
        self.latency_canvas.draw()

        # Обновление графика использования CPU
        self.cpu_plot.clear()
        for node_id in self.nodes:
            times = list(range(len(self.metrics_data[node_id]["cpu"])))
            cpu_usages = self.metrics_data[node_id]["cpu"]
            self.cpu_plot.plot(times, cpu_usages, label=f"Узел {node_id}")
        self.cpu_plot.legend(loc='upper right')
        self.cpu_plot.set_title("Использование CPU (%)", fontsize=12, fontweight='bold', pad=20)
        self.cpu_plot.set_xlabel("Время (условные единицы)", fontsize=10, labelpad=15)
        self.cpu_plot.set_ylabel("Использование CPU (%)", fontsize=10, labelpad=15)
        self.cpu_plot.grid(True)
        self.cpu_canvas.draw()

        # Обновление графика использования памяти
        self.memory_plot.clear()
        for node_id in self.nodes:
            times = list(range(len(self.metrics_data[node_id]["memory"])))
            memory_usages = self.metrics_data[node_id]["memory"]
            self.memory_plot.plot(times, memory_usages, label=f"Узел {node_id}")
        self.memory_plot.legend(loc='upper right')
        self.memory_plot.set_title("Использование памяти (МБ)", fontsize=12, fontweight='bold', pad=20)
        self.memory_plot.set_xlabel("Время (условные единицы)", fontsize=10, labelpad=15)
        self.memory_plot.set_ylabel("Использование памяти (МБ)", fontsize=10, labelpad=15)
        self.memory_plot.grid(True)
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

            if len(self.metrics_data[node_id]["latency"]) > self.max_data_points:
                self.metrics_data[node_id]["latency"].pop(0)
                self.metrics_data[node_id]["cpu"].pop(0)
                self.metrics_data[node_id]["memory"].pop(0)

            # Логируем генерацию данных
            self.ui_logger.debug(f"Узел {node_id}: задержка={self.metrics_data[node_id]['latency'][-1]}мс, CPU={self.metrics_data[node_id]['cpu'][-1]:.2f}%, память={self.metrics_data[node_id]['memory'][-1]:.2f}МБ")

    def generate_logs(self):
        # Генерация логов каждые 100 мс
        self.ui_logger.debug("Обновление данных...")
        self.ui_logger.info(f"Текущее время: {time.strftime('%H:%M:%S')}")
        self.root.after(100, self.generate_logs)

    def log_message(self, message):
        self.ui_queue.put(("log_message", message))
