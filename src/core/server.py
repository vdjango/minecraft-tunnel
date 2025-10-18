import asyncio
from common.utils import setup_logging, load_config
from core.base import App
from node.master import MasterServer
from node.worker import WorkerServer

class NodeApp(App):
    """高性能隧道服务器"""
    node_server = {
        'master': MasterServer,
        'worker': WorkerServer
    }
    
    def __init__(self, config_path: str = "config/server.conf"):
        super(NodeApp, self).__init__(load_config(config_path))
        self.node_type = self.config.get('node').get('node_type', 'worker')  # 默认作为Worker  master worker
    
    async def executor(self):
        return self.node_server[self.node_type]
    
    async def start(self):
        """启动服务器，根据节点类型选择对应节点"""
        runx = await self.executor()
        self.server = runx(self.config)
        await self.server.start()

    async def shutdown(self):
        """执行关闭操作"""
        await self.server.stop()
        print('NodeApp 执行关闭操作')
