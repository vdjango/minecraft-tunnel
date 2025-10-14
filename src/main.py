#!/usr/bin/env python3
"""
高性能Minecraft隧道服务器主程序
采用多进程 + 异步IO架构，支持数万并发连接
"""

import asyncio
import logging
import signal
import sys
from typing import Dict, Any

from core.server import TunnelServer
from common.utils import setup_logging, load_config
from monitor.metrics import MetricsCollector


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        # logger.FileHandler("tunnel_host.log"),
        logging.StreamHandler()
    ]
)



class TunnelServerApp:
    """隧道服务器应用程序"""
    
    def __init__(self, config_path: str = "config/server.conf"):
        self.logger = logging.getLogger("TunnelServerApp")
        self.config = load_config(config_path)
        self.server = None
        self.metrics = MetricsCollector()
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        """设置信号处理器"""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """信号处理"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        if self.server:
            asyncio.create_task(self.server.graceful_shutdown())
    
    async def run(self):
        """运行服务器"""
        try:
            # 初始化服务器
            self.server = TunnelServer(self.config)
            
            # 启动服务器
            await self.server.start()
            
        except Exception as e:
            self.logger.error(f"Server error: {e}")
            raise
    
    async def stop(self):
        """停止服务器"""
        if self.server:
            await self.server.stop()

async def main():
    """主函数"""
    logger = logging.getLogger("TunnelServerApp")
    # 设置日志
    setup_logging("config/logger.conf")
    
    # 创建并运行应用
    app = TunnelServerApp()
    
    try:
        await app.run()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server crashed: {e}")
        sys.exit(1)
    finally:
        await app.stop()

if __name__ == "__main__":
    # 设置事件循环策略（使用uvloop如果可用）
    # try:
    #     import uvloop
    #     asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    # except ImportError:
    #     pass
    
    asyncio.run(main())
