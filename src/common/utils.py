import logging
import logging.config
import configparser
import json
import os
import socket
import asyncio
from typing import Dict, Any, Optional


import logging
import codecs


class UTF8FileHandler(logging.FileHandler):
    """支持 UTF-8 编码的文件处理器"""
    
    def __init__(self, filename, mode='a', encoding='utf-8', delay=False):
        super().__init__(filename, mode, encoding, delay)


def setup_logging(config_path: str):
    """根据配置文件设置日志"""
    if os.path.exists(config_path):
        try:
            with open(config_path, 'rt') as f:
                config = json.load(f)
            logging.config.dictConfig(config)
            return
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error loading logging config: {e}")
    
    # 默认日志配置
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            UTF8FileHandler("tunnel.log"),
            logging.StreamHandler()
        ]
    )

def load_config(config_path: str) -> Dict[str, Any]:
    """加载配置文件"""
    config = configparser.ConfigParser()
    config.read(config_path)
    
    # 将配置转换为字典
    config_dict = {}
    for section in config.sections():
        config_dict[section] = dict(config[section])
    
    return config_dict

def get_local_ip() -> str:
    """获取本机IP地址"""
    try:
        # 创建一个临时socket连接到外部地址
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        import traceback
        traceback.print_exc()
        return "127.0.0.1"

def create_task_safe(coro) -> asyncio.Task:
    """安全创建异步任务，捕获异常"""
    task = asyncio.create_task(coro)
    task.add_done_callback(_handle_task_exception)
    return task

def _handle_task_exception(task: asyncio.Task):
    """处理任务异常"""
    try:
        task.result()
    except asyncio.CancelledError:
        pass  # 任务被取消是正常的
    except Exception as e:
        import traceback
        traceback.print_exc()
        logging.error(f"Task failed: {e}", exc_info=True)

def parse_address(address: str) -> Optional[tuple]:
    """解析地址字符串 (host:port)"""
    parts = address.split(":")
    if len(parts) != 2:
        return None
    try:
        return (parts[0], int(parts[1]))
    except ValueError:
        import traceback
        traceback.print_exc()    
        return None
