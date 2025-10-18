import signal
import logging
import asyncio

from typing import Dict
from abc import ABC, abstractmethod
from core.signal import SignalHandler


class BaseX(ABC):
    def __init__(self, config: Dict, event: asyncio.Event = asyncio.Event()):
        self.config: Dict = config
        self.node_id = '节点唯一ID'
        self._shutdown_event: asyncio.Event = event
        self._signal_down: bool = False
        self._signal_handlers_set: bool = False
        self.logger = logging.getLogger(f"[APP] BaseX {self.__class__.__name__}")

    async def event_loop(self):
        """事件循环"""
        while not self._signal_down and not self._shutdown_event.is_set():
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
                self.logger.error(f"事件循环错误: {e}")
                import traceback
                traceback.print_exc()
                break

    @abstractmethod
    async def start(self):
        """启动节点"""
        await self.event_loop()

    @abstractmethod
    async def shutdown(self):
        """执行关闭操作
        await self.stop() to -> await self.shutdown()"""
        pass

    async def tasks_cancel(self):
        """取消所有任务"""
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        
        # 等待任务取消
        await asyncio.gather(*tasks, return_exceptions=True)

    async def stop(self):
        await self.shutdown()
        await self.tasks_cancel()
        # 下面必须最后设置，否则 会导致主进程提前与子进程退出
        self._signal_down = True
        self._shutdown_event.set()


class App(BaseX, SignalHandler):
    """节点基类，提供最基础的功能"""

    def __init__(self, config: Dict, node_type: str = 'master'):
        super(App, self).__init__(config)
        self.node_type = node_type
        self.setup_signal_handlers()  # 设置信号处理
    
    @abstractmethod
    async def start(self):
        """启动服务器，根据节点类型选择运行模式"""
        
    async def run(self):
        """启动服务器，根据节点类型选择运行模式"""
        await self.start()
        await self.event_loop()  # 等待服务器停止
