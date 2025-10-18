#!/usr/bin/env python3
"""
高性能Minecraft隧道服务器主程序
采用多进程 + 异步IO架构，支持数万并发连接
"""

import asyncio
import logging
import sys

from core.server import NodeApp
from common.utils import setup_logging

logger = logging.getLogger("App")


class ServerApp(NodeApp):
    """隧道服务器应用程序"""
    def __init__(self, config_path: str = "config/server.conf"):
        super(ServerApp, self).__init__(config_path)
    

async def main():
    """主函数"""
    # 设置日志
    setup_logging("config/logger.conf")
    
    # 创建并运行应用
    app = ServerApp()
    
    try:
        await app.run()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"Server crashed: {e}")
        # 确保执行关闭流程
        await app.stop()
        sys.exit(1)


if __name__ == "__main__":
    # 设置事件循环策略（使用uvloop如果可用）
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass
    
    asyncio.run(main())
