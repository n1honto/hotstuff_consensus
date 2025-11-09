import asyncio
from node import HotStuffNode
from network import HotStuffNetwork
from ui import HotStuffUI
from monitor import NetworkMonitor
import threading
import tkinter as tk
import logging

logging.basicConfig(level=logging.INFO)

def run_network(nodes):
    network = HotStuffNetwork(nodes)
    asyncio.run(network.start())

def main():
    nodes = [
        HotStuffNode(0, [0, 1, 2, 3, 4, 5], "127.0.0.1", 5000, shard_id=0),
        HotStuffNode(1, [0, 1, 2, 3, 4, 5], "127.0.0.1", 5001, shard_id=0),
        HotStuffNode(2, [0, 1, 2, 3, 4, 5], "127.0.0.1", 5002, shard_id=1),
        HotStuffNode(3, [0, 1, 2, 3, 4, 5], "127.0.0.1", 5003, shard_id=1),
        HotStuffNode(4, [0, 1, 2, 3, 4, 5], "127.0.0.1", 5004, shard_id=0),
        HotStuffNode(5, [0, 1, 2, 3, 4, 5], "127.0.0.1", 5005, shard_id=1, is_byzantine=True)
    ]

    monitor = NetworkMonitor()
    for node in nodes:
        node.monitor = monitor

    network_thread = threading.Thread(target=run_network, args=(nodes,))
    network_thread.daemon = True
    network_thread.start()

    root = tk.Tk()
    ui = HotStuffUI(root, [node.node_id for node in nodes])
    root.mainloop()

if __name__ == "__main__":
    main()
