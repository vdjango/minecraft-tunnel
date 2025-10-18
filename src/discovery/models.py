from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from enum import IntEnum
import time

from network.protocol import NodeType


@dataclass
class NodeInfo:
    """节点信息"""
    node_id: str
    host: str
    port: int
    node_type: str  # 'master' or 'worker'
    load: float = 0.0  # 当前负载 0-1
    last_heartbeat: float = field(default_factory=time.time)
    is_active: bool = True
    capacity: int = 100  # 
    capabilities: Dict[str, Any] = field(default_factory=dict)  # 节点能力描述
    current_connections: int = 0  # 当前连接数
    max_connections: int = 1000   # 最大支持连接数

@dataclass
class WorkerInfo:
    """Worker信息"""
    worker_id: str
    version: int
    protocol_version: int
    capabilities: int
    address: tuple
    last_seen: float = time.time()
    is_online: bool = True

@dataclass
class ConnectionStats:
    """连接统计信息"""
    bytes_sent: int = 0
    bytes_received: int = 0
    packets_sent: int = 0
    packets_received: int = 0
    connected_at: float = time.time()
    last_activity: float = time.time()
