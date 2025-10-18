import asyncio
import logging
import time
import struct
import signal
import os

from typing import Dict, Any, Optional, List

from network.connection import ConnectionManagerSingleton, create_connection_manager
from network.protocol import NodeType, PacketType, ActionType, ConnectionState
from network.exceptions import ConnectionClosedError, HandshakeError
from node.base import mp
from discovery.models import NodeInfo
from discovery.registry import ServiceRegistry
from core.plugin.manager import PluginManager
from core.plugin.types import PluginEvent, PluginEventType
from core.plugin.types import PluginNodeType
from node.mixin import NodeMixinSet


class NodeExecutor:
    """隧道工作进程"""
    
    def __init__(self, worker_id: int, config: Dict, registry):
        self.worker_id = worker_id
        self.config = config
        self.registry: ServiceRegistry = registry
        self._shutting_down = False
        self._shutdown_event = asyncio.Event()
        self._shutdown_task = None  # 用于跟踪关闭任务
        self.logger = logging.getLogger(f"[{worker_id}] Master")
        self.max_connections = 1000
        self.current_connections = 0
        self.connection_semaphore = asyncio.Semaphore(self.max_connections)

        # 确定节点类型
        node_type_str = self.config.get('node', {}).get('node_type', 'master')
        self.node_type = PluginNodeType.MASTER
        
        # 初始化插件管理器
        self.plugin_manager: Optional[PluginManager] = PluginManager(self.worker_id, self.config, self.node_type, self.registry)
        # 创建连接管理器
        self.connection_manager = ConnectionManagerSingleton.get_instance(config, self.plugin_manager)
    
    def _setup_signal_handlers(self):
        """设置信号处理器"""
        # 获取主事件循环
        loop = asyncio.get_running_loop()
        # 注册信号处理
        for sig in [signal.SIGTERM, signal.SIGINT]:
            loop.add_signal_handler(sig, lambda s=sig: self._signal_handler(s))

    def _signal_handler(self, signum):
        """信号处理"""
        self.logger.debug(f"收到信号 {signum}，正在关闭...")
        
        # 如果已经有关闭任务在运行，则不再创建新任务
        if self._shutdown_task is None:
            self._shutdown_task = asyncio.create_task(self._cleanup())

    async def run(self):
        """运行工作进程"""
        # 设置信号处理
        self._setup_signal_handlers()

        # 初始化插件管理器
        await self.plugin_manager.initialize()
        # 启动连接管理器
        await self.connection_manager.start()

        # 启动事件循环
        await self._event_loop()

    async def _event_loop(self):
        """事件循环"""
        # 等待关闭事件或处理其他任务
        while not self._shutting_down:
            try:
                # 等待关闭事件或超时
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=0.5
                )
                break
            except asyncio.TimeoutError:
                # 超时后继续循环，检查关闭标志
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                import traceback
                traceback.print_exc()

                self.logger.error(f"事件循环发生错误: {e}")
                break

    async def _cleanup(self):
        """清理资源"""
        self.logger.debug(f"正在退出进程 {self.worker_id}")

        # 发送节点停止事件
        await self.plugin_manager.emit_event(
            PluginEvent(
                PluginEventType.NODE_STOP,
                self,
                {'node_type': self.node_type}
            )
        )
        
        # 关闭插件管理器
        await self.plugin_manager.shutdown()

        # 取消所有任务
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
            
        # 等待任务取消
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # 关闭所有活跃连接
        # 确保关闭连接管理器
        await self.connection_manager.stop()
        await self.plugin_manager.shutdown()
        self._shutting_down = True
        self._shutdown_event.set()


class MasterServer(NodeMixinSet):
    """主节点服务，负责协调节点分发和管理工作节点
    1. 注册社区服务节点（部署的节点服务器需要加入网络）
    2. 请求分配节点（玩家联机时请求分配的节点主机）"""

    node_executor = NodeExecutor
    
    def __init__(self, config: Dict):
        super(MasterServer, self).__init__(config)
        self.workers: List[mp.Process] = []
        self.worker_restart_attempts: Dict[int, int] = {}  # 记录工作进程重启次数

        self.registry = ServiceRegistry(config)
        self.logger = logging.getLogger(f"[MAIN] NodeX {self.__class__.__name__}")
    
    async def set_node_id(self):
        self.node_id = 'Master节点唯一ID'

    async def run_until(self, worker_id, *args):
        worker = self.node_executor(worker_id, *args)
        await worker.run()
    
    async def start(self):
        """启动主节点"""
        # 启动API服务，供Worker节点注册和心跳
        # TODO API服务是否需要放入工作进程中？ 会不会有问题等
        await self._start_api_server()
        self.workers = await self.start_worker(self.config, self.registry, worker_processes=8)
        asyncio.create_task(self.start_monitor(self.config, self.registry))

    async def _start_api_server(self):
        """启动API服务器"""
        self.logger.info('启动API服务')
        pass
