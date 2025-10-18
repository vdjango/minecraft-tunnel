import asyncio
import logging
import time
import struct
import signal
import os
import abc

from typing import Dict, Any, Optional, List

from common.utils import setup_logging
from node.base import BaseX, mp # NodeX, 


class NodeStartWorkerMixin:
    """Mixin提供节点启动，实现子进程启动方法"""

    @abc.abstractmethod
    async def run_until(self, worker_id, *args, **kwargs):
        """启动的子进程"""
        pass

    async def create_worker(self, worker_id: Any, *args, **kwargs):
        def _worker(worker_id: Any, *args):
            setup_logging("config/logger.conf")
            logger = logging.getLogger(f"[{worker_id}] Main")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.run_until(worker_id, *args, **kwargs))
            except Exception as e:
                import traceback
                traceback.print_exc()
                
                logger.error(f"启动节点失败，错误信息: {e}")
            finally:
                loop.close()

        worker = mp.Process(
            target=_worker,
            args=(worker_id, *args),
            name=f"MasterNode-{worker_id}"
        )
        worker.start()
        return worker

    async def start_worker(self, *args, worker_processes: str = 'auto', **kwargs):
        """启动节点"""  # , **kwargs
        worker_count = mp.cpu_count()
        if worker_processes != 'auto':
            worker_count = int(worker_processes)
        
        workers = []
        for i in range(worker_count):
            workers.append(await self.create_worker(i, *args, **kwargs))
        
        return workers

    async def restart_worker(self, worker_index: int, *args):
        """重启工作进程"""
        # 清理旧进程（如果存在）
        if worker_index < len(self.workers) and self.workers[worker_index].is_alive():
            self.workers[worker_index].terminate()
            self.workers[worker_index].join(timeout=5)

        # 创建新工作进程
        new_worker = await self.create_worker(worker_index, *args)

        # 更新进程列表
        if worker_index < len(self.workers):
            self.workers[worker_index] = new_worker
        else:
            self.workers.append(new_worker)

        self.logger.info(f"已成功重新启动工作进程 {worker_index}")
        # 等待进程启动完成
        await asyncio.sleep(1)


class NodeTerminationMixin:
    """工作节点"""

    async def wait_for_termination(self, timeout: int = 10):
        """等待工作进程终止"""
        start_time = time.time()
        terminated_count = 0
        while time.time() - start_time < timeout:
            terminated_count = 0
            # 检查进程状态
            for worker in self.workers:
                if not worker.is_alive():
                    terminated_count += 1
            
            if terminated_count >= len(self.workers):  # TODO 已完成·这里
                return
            
            await asyncio.sleep(0.5)
    
        self.logger.warning("等待进程终止超时")
    
    async def force_terminate(self):
        """强制终止仍在运行的进程"""
        for worker in self.workers:
            try:
                # 检查进程是否仍在运行
                os.kill(worker.pid, 0)
                os.kill(worker.pid, signal.SIGKILL)
            except ProcessLookupError:
                # 进程已终止
                pass
            except Exception as e:
                import traceback
                traceback.print_exc()


class NodeMonitorMixin:

    async def start_monitor(self, *agrs, check_interval: int = 5):
        """监控工作进程状态"""
        while not self._signal_down and not self._shutdown_event.is_set():
            await asyncio.sleep(check_interval)
            active_workers = 0
            for i, worker in enumerate(self.workers):
                if self._signal_down:
                    break
                if not worker.is_alive():
                    # 重启工作进程
                    self.logger.warning(f"进程 {i} (PID {worker.pid}) 已死亡，正在重新启动...")
                    await self.restart_worker(i, *agrs)
                    continue

                active_workers += 1
            

class NodeMixinSet(BaseX, NodeStartWorkerMixin, NodeTerminationMixin, NodeMonitorMixin):

    def __init__(self, config: Dict):
        super(NodeMixinSet, self).__init__(config)
        self.node_id = '节点唯一ID'
        self.workers: List[mp.Process] = []
        self.logger = logging.getLogger(f"[MAIN] NodeX {self.__class__.__name__}")
    
    @abc.abstractmethod
    async def set_node_id(self):
        self.node_id = '节点唯一ID'

    @abc.abstractmethod
    async def start(self):
        """启动主节点"""
        self.workers = await self.start_worker(self.config, worker_processes=8)
        asyncio.create_task(self.start_monitor(self.config))

    async def shutdown(self, timeout: int = 10):
        """停止所有工作进程"""
        if not self.workers:
            return
        
        # 发送SIGTERM信号给所有工作进程
        for worker in self.workers:
            try:
                os.kill(worker.pid, signal.SIGTERM)
                self.logger.debug(f"向工作进程发送 SIGTERM 信号 {worker.pid}")
            except ProcessLookupError:
                self.logger.warning(f"进程 {worker.pid} 已终止")
            except Exception as e:
                import traceback
                traceback.print_exc()
                
                self.logger.error(f"停止进程时出错 {worker.pid}: {e}")
        
        # 等待进程终止
        await self.wait_for_termination(timeout)
        
        # 强制终止仍在运行的进程
        await self.force_terminate()
        
        # 清理进程列表
        self.workers.clear()
        self.logger.info("完成！")
    