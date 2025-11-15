import asyncio
import random
from typing import List
from node import HotStuffNode

class HotStuffNetwork:
    def __init__(self, nodes: List[HotStuffNode]):
        self.nodes = nodes

    async def start(self):
        servers = []
        for node in self.nodes:
            server = await asyncio.start_server(
                node.handle_message,
                host=node.host,
                port=node.port
            )
            servers.append(server)
            asyncio.create_task(self.run_node(node))

        async with servers[0]:
            await servers[0].serve_forever()

    async def run_node(self, node: HotStuffNode):
        await asyncio.sleep(1)
        while True:
            transactions = [{"from": f"Node_{random.randint(0, 999)}", "to": f"Node_{random.randint(0, 999)}", "amount": random.randint(1, 100)} for _ in range(random.randint(1, 10))]
            await node.run_consensus_round()
            await asyncio.sleep(3)
