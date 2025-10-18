import struct
from enum import IntEnum, Enum
from typing import Dict, Any


class PacketType(IntEnum):
    """数据包类型枚举"""
    HANDSHAKE_REQUEST = 0x01    # 握手请求
    HANDSHAKE_RESPONSE = 0x02   # 握手响应
    AUTH_REQUEST = 0x03         # 认证请求
    AUTH_RESPONSE = 0x04        # 认证响应
    REGISTER_NODE = 0x05        # 注册节点
    REQUEST_NODE = 0x06         # 请求节点
    HEARTBEAT = 0x07            # 心跳包
    STATUS_UPDATE = 0x08        # 状态更新
    DISCONNECT = 0x09           # 断开连接
    CUSTOM_EVENT = 0x0A         # 自定义事件


class ActionType(IntEnum):
    """指令类型枚举"""
    REGISTER_NODE = 0x01
    REQUEST_NODE = 0x02
    HEARTBEAT = 0x03
    STATUS_UPDATE = 0x04
    DISCONNECT = 0xFF


class ConnectionState(Enum):
    """连接状态枚举"""
    CONNECTED = "connected"          # 已连接
    HANDSHAKING = "handshaking"      # 握手中
    AUTHENTICATING = "authenticating" # 认证中
    READY = "ready"                  # 就绪
    CLOSING = "closing"              # 关闭中
    CLOSED = "closed"                # 已关闭
    ERROR = "error"                  # 错误


class NodeType(IntEnum):
    """客户端节点类型枚举"""
    COMMUNITY_NODE = 0x01  # 社区节点​
    PLAYER_HOST = 0x02     # 玩家主机​
    PLAYER_CLIENT = 0x03   # 玩家客户端​


def unpack_header(data: bytes) -> tuple:
    """解包数据包头"""
    return struct.unpack('!BH', data)

def pack_header(packet_type: int, length: int) -> bytes:
    """打包数据包头"""
    return struct.pack('!BH', packet_type, length)

def unpack_byte(data: bytes) -> int:
    """解包单个字节 (B)"""
    return struct.unpack('!B', data)[0]

def unpack_ushort(data: bytes) -> int:
    """解包无符号短整型 (H)"""
    return struct.unpack('!H', data)[0]

def unpack_ulong(data: bytes) -> int:
    """解包无符号长整型 (I)"""
    return struct.unpack('!I', data)[0]

def unpack_ulonglong(data: bytes) -> int:
    """解包无符号长长整型 (Q)"""
    return struct.unpack('!Q', data)[0]

def unpack_byte_ushort(data: bytes) -> tuple:
    """解包字节+无符号短整型 (BH)"""
    return struct.unpack('!BH', data)

def unpack_byte_byte(data: bytes) -> tuple:
    """解包两个字节 (BB)"""
    return struct.unpack('!BB', data)

def unpack_byte_byte_byte(data: bytes) -> tuple:
    """解包三个字节 (BBB)"""
    return struct.unpack('!BBB', data)

def pack_byte(value: int) -> bytes:
    """打包单个字节 (B)"""
    return struct.pack('!B', value)

def pack_ushort(value: int) -> bytes:
    """打包无符号短整型 (H)"""
    return struct.pack('!H', value)

def pack_ulong(value: int) -> bytes:
    """打包无符号长整型 (I)"""
    return struct.pack('!I', value)

def pack_ulonglong(value: int) -> bytes:
    """打包无符号长长整型 (Q)"""
    return struct.pack('!Q', value)

def pack_byte_ushort(byte_value: int, ushort_value: int) -> bytes:
    """打包字节+无符号短整型 (BH)"""
    return struct.pack('!BH', byte_value, ushort_value)

def pack_byte_byte(byte1: int, byte2: int) -> bytes:
    """打包两个字节 (BB)"""
    return struct.pack('!BB', byte1, byte2)

def pack_byte_byte_byte(byte1: int, byte2: int, byte3: int) -> bytes:
    """打包三个字节 (BBB)"""
    return struct.pack('!BBB', byte1, byte2, byte3)

def pack_ushort_ushort_byte(ushort1: int, ushort2: int, byte: int) -> bytes:
    """打包两个无符号短整型和一个字节 (HHB)"""
    return struct.pack('!HHB', ushort1, ushort2, byte)

def unpack_ushort_ushort_byte(data: bytes) -> tuple:
    """解包两个无符号短整型和一个字节 (HHB)"""
    return struct.unpack('!HHB', data)

def unpack_handshake(data: bytes) -> Dict[str, Any]:
    """解包握手数据"""
    # 握手包格式: 版本(1B) | 协议版本(1B) | ID长度(1B) | ID(变长) | 能力标志(1B)
    version, protocol_version, id_length = unpack_byte_byte_byte(data[:3])
    worker_id = data[3:3+id_length].decode('utf-8')
    capabilities = data[3+id_length] if len(data) > 3+id_length else 0
    
    return {
        'version': version,
        'protocol_version': protocol_version,
        'id': worker_id,
        'capabilities': capabilities
    }

def pack_handshake_response(status: int, server_version: int, capabilities: int) -> bytes:
    """打包握手响应"""
    return pack_byte_byte_byte(status, server_version, capabilities)

