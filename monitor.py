import time
import psutil
import matplotlib.pyplot as plt
from collections import defaultdict

class NetworkMonitor:
    def __init__(self):
        self.metrics = defaultdict(list)
        self.start_time = time.time()
        self.process = psutil.Process()

    def log_metric(self, node_id: int, metric: str, value: float):
        self.metrics[(node_id, metric)].append((time.time() - self.start_time, value))

    def log_cpu_memory(self, node_id: int):
        cpu_percent = self.process.cpu_percent() / psutil.cpu_count()
        mem_info = self.process.memory_info().rss / (1024 * 1024)  # in MB
        self.log_metric(node_id, "cpu_usage", cpu_percent)
        self.log_metric(node_id, "memory_usage", mem_info)

    def plot_metrics(self):
        plt.figure(figsize=(15, 10))
        metrics_to_plot = [
            ("messages_sent", "Messages Sent", "steps"),
            ("messages_received", "Messages Received", "steps"),
            ("latency", "Latency (s)", "plot"),
            ("cpu_usage", "CPU Usage (%)", "plot"),
            ("memory_usage", "Memory Usage (MB)", "plot")
        ]

        for i, (metric_name, label, plot_type) in enumerate(metrics_to_plot, 1):
            plt.subplot(3, 2, i)
            for (node_id, metric), values in self.metrics.items():
                if metric == metric_name:
                    times, vals = zip(*values)
                    if plot_type == "steps":
                        plt.step(times, vals, where="post", label=f"Node {node_id}")
                    else:
                        plt.plot(times, vals, label=f"Node {node_id}")
            plt.xlabel("Time (s)")
            plt.ylabel(label)
            plt.legend()
            plt.title(label)
            plt.grid()

        plt.tight_layout()
        plt.savefig("network_metrics.png")
        plt.close()
