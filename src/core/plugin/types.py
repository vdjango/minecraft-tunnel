from enum import Enum, IntEnum, auto
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

class PluginEventType(Enum):
    """插件事件类型"""
    # 生命周期事件
    PLUGIN_LOAD = auto()           # 插件加载
    PLUGIN_INIT = auto()           # 插件初始化
    PLUGIN_ENABLE = auto()         # 插件启用
    PLUGIN_DISABLE = auto()        # 插件禁用
    PLUGIN_UNLOAD = auto()         # 插件卸载
    PLUGIN_ERROR = auto()          # 插件错误
    
    # 节点事件
    NODE_REGISTER = auto()         # 节点注册
    NODE_START = auto()            # 节点启动
    NODE_READY = auto()            # 节点就绪
    NODE_STOP = auto()             # 节点停止
    NODE_SHUTDOWN = auto()         # 节点关闭
    
    # 心跳事件
    HEARTBEAT = auto()             # 心跳

    # 数据事件
    DATA_RECEIVED = auto()         # 数据接收
    DATA_PROCESSED = auto()        # 数据处理
    DATA_SENT = auto()             # 数据发送
    
    # 服务事件
    SERVICE_REGISTER = auto()      # 服务注册
    SERVICE_UNREGISTER = auto()    # 服务注销
    SERVICE_UPDATE = auto()        # 服务更新
    
    # 连接事件
    CONNECTION_ACCEPTED = auto()      # 连接接受
    CONNECTION_HANDSHAKE = auto()     # 连接握手
    CONNECTION_AUTHENTICATED = auto() # 连接认证
    CONNECTION_READY = auto()         # 连接就绪
    CONNECTION_DATA_RECEIVED = auto() # 数据接收
    CONNECTION_DATA_SENT = auto()     # 数据发送
    CONNECTION_TIMEOUT = auto()       # 数据超时
    CONNECTION_CLOSED = auto()        # 连接关闭
    CONNECTION_ERROR = auto()         # 连接错误
    
    # 数据包事件
    PACKET_RECEIVED = auto()          # 数据包接收
    PACKET_PROCESSED = auto()         # 数据包处理
    PACKET_SENT = auto()              # 数据包发送
    
    # 服务事件
    SERVICE_REGISTERED = auto()       # 服务注册
    SERVICE_UNREGISTERED = auto()     # 服务注销
    SERVICE_UPDATED = auto()          # 服务更新
    
    # 自定义事件
    CUSTOM_EVENT = auto()


@dataclass
class PluginEvent:
    """插件事件（扩展版）"""
    event_type: PluginEventType
    source: Any
    data: Optional[Dict] = None
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            import time
            self.timestamp = time.time()


@dataclass
class ConnectionEventData:
    """连接事件数据"""
    connection_id: str
    client_addr: tuple
    connection: Any
    data: Optional[bytes] = None
    error: Optional[str] = None


@dataclass
class PacketEventData:
    """数据包事件数据"""
    packet_type: int
    packet_data: bytes
    connection_id: str
    client_addr: tuple


class PluginNodeType(IntEnum):
    """服务端节点类型"""
    MASTER = 0x01  # "master"   # Master 节点
    WORKER = 0x02  # "worker"   # Worker 节点
    ALL = 0x03  # "all"         # 适用于所有节点类型
# class NodeType(IntEnum):
#     """客户端节点类型枚举"""
#     COMMUNITY_NODE = 0x01  # 社区节点​
#     PLAYER_HOST = 0x02     # 玩家主机​
#     PLAYER_CLIENT = 0x03   # 玩家客户端​

class PluginPriority(IntEnum):
    """插件优先级枚举"""
    LOWEST = 0      # 最低优先级
    LOW = 1         # 低优先级
    NORMAL = 2      # 正常优先级
    HIGH = 3        # 高优先级
    HIGHEST = 4     # 最高优先级
    CRITICAL = 5    # 关键优先级（系统核心插件）


@dataclass
class PluginInfo:
    """插件信息"""
    id: str
    name: str
    version: str
    description: str
    author: str
    node_types: List[PluginNodeType]  # 支持的节点类型
    priority: PluginPriority
    dependencies: List[str]
    config: Dict[str, Any]
    state: str
