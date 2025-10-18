

import asyncio
import logging
import signal

from abc import ABC, abstractmethod


class SignalHandler(ABC):
    _signal_down: bool = False
    _signal_handlers_set: bool = False
    logger = logging.getLogger(f"[Signal] {__name__}")

    def setup_signal_handlers(self):
        """设置信号处理器"""
        if self._signal_handlers_set:
            return
        
        try:
            loop = asyncio.get_running_loop()
            
            # 注册信号处理
            for sig in [signal.SIGTERM, signal.SIGINT]:
                loop.add_signal_handler(sig, self._create_signal_handler(sig))
                self.logger.debug(f"注册信号 {signal.Signals(sig).name}")
            
            self._signal_handlers_set = True
        except NotImplementedError:
            import traceback
            traceback.print_exc()
            self.logger.warning("此平台不支持信号处理")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.logger.error(f"设置信号处理时出错: {e}")
    
    def _create_signal_handler(self, signum):
        """创建信号处理器（避免闭包问题）"""
        def handler():
            self._signal_handler(signum)
        return handler
    
    def _signal_handler(self, signum):
        """信号处理"""
        if self._signal_down:
            return
        
        signame = signal.Signals(signum).name
        self.logger.debug(f"收到信号 {signame}, 主进程正在关闭...")
        
        # 创建关闭任务
        asyncio.create_task(self.stop())
    
    @abstractmethod
    async def stop(self):
        self._signal_down = True
