# 网络通信协议技术文档

## 文档概述

本文档定义了节点间通信的协议标准、数据包格式、类型定义及编码规范，作为后续开发的技术标准和代码规范。本文档旨在为开发团队提供清晰、详细的技术参考，确保系统的一致性和可维护性。

### 1. 协议概述

#### 1.1 设计原则

* ​网络字节序​​：所有数据包使用大端序（Big-Endian）
* ​​类型明确​​：每个数据包有明确的类型标识
* ​​扩展性​​：协议设计支持未来扩展
* 错误处理​​：包含完善的错误处理机制

#### 1.2 通信流程

* TCP连接建立
* 握手协议交换
* 身份认证
* 数据交换
* 连接关闭

### 2. 数据包通用格式

#### 2.1 数据包结构

```bash
+----------------+----------------+----------------+
|  包类型 (1B)   |  数据长度 (2B) |    数据 (变长)  |
+----------------+----------------+----------------+
```

#### 2.2 包头格式

更多参考 `src/network/protocol.py`

```python
# 打包包头
def pack_header(packet_type: int, length: int) -> bytes:
    return struct.pack('!BH', packet_type, length)

# 解包包头
def unpack_header(data: bytes) -> tuple:
    return struct.unpack('!BH', data)
```

### 3. 数据包类型定义

#### 3.1 包类型枚举 (PacketType)

更多参考 `src/network/protocol.py`

```python
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
```

#### 3.2 节点类型枚举 (NodeType)
```python
class NodeType(IntEnum):
    """节点类型枚举"""
    COMMUNITY_NODE = 0x01      # 社区节点
    PLAYER_HOST = 0x02         # 玩家主机
    PLAYER_CLIENT = 0x03       # 玩家客户端
    ALL = 0xFF                 # 所有节点类型
```

#### 3.3 连接状态枚举 (ConnectionState)
```python
class ConnectionState(Enum):
    """连接状态枚举"""
    CONNECTED = "connected"          # 已连接
    HANDSHAKING = "handshaking"     # 握手中
    AUTHENTICATING = "authenticating" # 认证中
    READY = "ready"                 # 就绪
    CLOSING = "closing"             # 关闭中
    CLOSED = "closed"               # 已关闭
    ERROR = "error"                 # 错误
```

#### 3.4 插件优先级枚举 (PluginPriority)
```python
class PluginPriority(IntEnum):
    """插件优先级枚举"""
    LOWEST = 0      # 最低优先级
    LOW = 1         # 低优先级
    NORMAL = 2      # 正常优先级
    HIGH = 3        # 高优先级
    HIGHEST = 4     # 最高优先级
    CRITICAL = 5    # 关键优先级（系统核心插件）
```

### 4. 具体数据包格式

#### 4.1 握手请求 (HANDSHAKE_REQUEST = 0x01)
​
**​格式​​：** 版本(1B) | 协议版本(1B) | ID长度(1B) | ID(变长) | 能力标志(1B)

打包方法​​：
```python
def pack_handshake_request(version: int, protocol_version: int, 
                          identifier: str, capabilities: int) -> bytes:
    identifier_bytes = identifier.encode('utf-8')
    body_data = struct.pack('!BBB', version, protocol_version, len(identifier_bytes))
    body_data += identifier_bytes
    body_data += struct.pack('!B', capabilities)
    return body_data
```

关于 `能力标志` 请参考 `附录A：Capabilities（能力标志）系统`

#### 4.2 握手响应 (HANDSHAKE_RESPONSE = 0x02)

**​​格式​​：** 状态(1B) | 服务器版本(1B) | 支持的能力(1B)

​​打包方法​​：

```python
def pack_handshake_response(status: int, server_version: int, 
                           supported_capabilities: int) -> bytes:
    return struct.pack('!BBB', status, server_version, supported_capabilities)
```

关于 `能力标志` 请参考 `附录A：Capabilities（能力标志）系统`

#### 4.3 认证请求 (AUTH_REQUEST = 0x03)

**​​格式​​：** 认证类型(1B) | 凭证长度(2B) | 凭证数据(变长)

​​打包方法​​：
```python
def pack_auth_request(auth_type: int, credential: bytes) -> bytes:
    cred_length = len(credential)
    body_data = struct.pack('!BH', auth_type, cred_length)
    body_data += credential
    return body_data
```

#### 4.4 节点注册 (REGISTER_NODE = 0x05)
​​
**格式​​：** 节点类型(1B) | 主机长度(1B) | 主机(变长) | 端口(2B) | 容量(2B) | 能力标志(1B)

​打包方法​​：
```python
def pack_register_node(node_type: int, host: str, port: int, 
                      capacity: int, capabilities: int) -> bytes:
    host_bytes = host.encode('utf-8')
    body_data = struct.pack('!B', node_type)
    body_data += struct.pack('!B', len(host_bytes))
    body_data += host_bytes
    body_data += struct.pack('!HHB', port, capacity, capabilities)
    return body_data
```

关于 `能力标志` 请参考 `附录A：Capabilities（能力标志）系统`

#### 4.5 心跳包 (HEARTBEAT = 0x07)
​
**​格式​​：** 时间戳(8B)

​打包方法​​：

```python
def pack_heartbeat(timestamp: int) -> bytes:
    return struct.pack('!Q', timestamp)
```

#### 4.6 状态更新 (STATUS_UPDATE = 0x08)

​​**格式​​：** 当前负载(2B) | 连接数(2B) | 状态标志(1B)

​​打包方法​​：
```python
def pack_status_update(current_load: int, connections: int, 
                     status_flags: int) -> bytes:
    return struct.pack('!HHB', current_load, connections, status_flags)
```

#### 4.7 断开连接 (DISCONNECT = 0x09)

**​​格式​​：** 原因长度(2B) | 原因(变长)

​​打包方法​​：
```python
def pack_disconnect(reason: str) -> bytes:
    reason_bytes = reason.encode('utf-8')
    body_data = struct.pack('!H', len(reason_bytes))
    body_data += reason_bytes
    return body_data
```

### 5. 响应格式标准

#### 5.1 通用响应格式

​**​格式​​：** 状态(1B) | 消息长度(2B) | 消息(变长) | 额外数据(变长)

**​​状态码定义​​：**
```python
0x00：成功
0x01：一般错误
0x02：超时
0x03：认证失败
0x04：无效参数
0x05：资源不足
0x06：不支持的操作
```

### 6. 插件系统规范

#### 6.1 插件事件类型 (PluginEventType)

更多参考 `src/core/plugin/types.py`

```python
class PluginEventType(Enum):
    """插件事件类型枚举"""
    PLUGIN_LOAD = auto()              # 插件加载
    PLUGIN_INIT = auto()              # 插件初始化
    PLUGIN_ENABLE = auto()            # 插件启用
    PLUGIN_DISABLE = auto()           # 插件禁用
    PLUGIN_UNLOAD = auto()            # 插件卸载
    PLUGIN_ERROR = auto()             # 插件错误
    
    NODE_START = auto()               # 节点启动
    NODE_READY = auto()               # 节点就绪
    NODE_STOP = auto()                # 节点停止
    NODE_SHUTDOWN = auto()            # 节点关闭
    
    CONNECTION_ACCEPTED = auto()      # 连接接受
    CONNECTION_HANDSHAKE = auto()     # 连接握手
    CONNECTION_AUTHENTICATED = auto() # 连接认证
    CONNECTION_READY = auto()         # 连接就绪
    CONNECTION_DATA_RECEIVED = auto() # 数据接收
    CONNECTION_DATA_SENT = auto()     # 数据发送
    CONNECTION_CLOSED = auto()        # 连接关闭
    CONNECTION_ERROR = auto()         # 连接错误
    
    PACKET_RECEIVED = auto()          # 数据包接收
    PACKET_PROCESSED = auto()         # 数据包处理
    PACKET_SENT = auto()              # 数据包发送
    
    CUSTOM_EVENT = auto()             # 自定义事件
```

#### 6.2 插件基类规范

更多参考 `src/core/plugin/base.py`

```python
class PluginBase(ABC):
    """插件基类规范"""
    
    # 元数据（必须定义）
    PLUGIN_NAME = "Unnamed Plugin"
    PLUGIN_VERSION = "1.0.0"
    PLUGIN_DESCRIPTION = "No description provided"
    PLUGIN_AUTHOR = "Unknown"
    PLUGIN_NODE_TYPES = [NodeType.ALL]  # 支持的节点类型
    PLUGIN_PRIORITY = PluginPriority.NORMAL
    PLUGIN_DEPENDENCIES = []  # 依赖的插件ID
    
    @abc.abstractmethod
    async def handle_event(self, event: PluginEvent) -> Optional[Any]:
        """处理事件"""
        pass
    
    @abc.abstractmethod
    async def execute(self, context: Dict) -> Any:
        """执行插件功能"""
        pass
```

### 7. 编码规范

#### 7.1 命名规范

```python
​​类名​​：使用驼峰命名法（如 PacketHandler）
​​方法名​​：使用蛇形命名法（如 parse_packet）
​​常量​​：使用大写字母和下划线（如 MAX_CONNECTIONS）
​​枚举值​​：使用大写字母和下划线（如 HANDSHAKE_REQUEST）
```

#### 7.2 日志规范

```python
# 日志格式
LOG_FORMAT = '%(asctime)s - [%(processName)s] %(name)s - %(levelname)s - %(message)s'

# 日志级别
LOG_LEVEL = logging.INFO

# 日志字段
# - asctime: 时间戳
# - processName: 进程名称
# - name: 日志器名称
# - levelname: 日志级别
# - message: 日志消息
```

#### 7.3 错误处理规范
```python
try:
    # 可能出错的操作
    result = await some_operation()
except SpecificException as e:
    logger.error(f"操作失败: {e}")
    # 返回错误响应
    return create_error_response(0x01, f"操作失败: {e}")
except Exception as e:
    logger.exception("未预期的错误")
    # 返回通用错误响应
    return create_error_response(0x01, "内部错误")
```

#### 7.4 类型注解规范
```python
def function_name(param: Type) -> ReturnType:
    """函数说明
    
    Args:
        param: 参数说明
        
    Returns:
        返回值说明
        
    Raises:
        ExceptionType: 异常说明
    """
    pass
```

### 8. 性能与安全

#### 8.1 性能优化

* 使用数据缓冲减少系统调用
* 合理设置超时时间
* 使用连接池管理资源
* 禁止阻塞操作

#### 8.2 安全考虑

* 所有通信使用认证机制
* 敏感数据加密传输
* 实施速率限制防止滥用
* 定期更新认证密钥

### 9. 版本管理

#### 9.1 协议版本

* 主版本​​：不兼容的协议更改
* ​​次版本​​：向后兼容的功能性新增
* 修订版本​​：问题修复

#### 9.2 向后兼容

* 新版本协议必须支持旧版本客户端
* 废弃的功能需要保留至少两个版本周期
* 提供版本协商机制

## 附录A：Capabilities（能力标志）系统

​**​附录A**​​ apabilities（能力标志）是一个位掩码系统，用于在客户端和服务器之间协商支持的功能。它允许：

* 功能协商​​：客户端和服务器(指Master、Worker节点)可以协商共同支持的功能
* ​版本兼容性​​：不同版本的实现可以互操作
* ​渐进式增强​​：新功能可以逐步添加
* ​明确的特性检测​​：可以准确检测对方支持的功能
* ​优雅降级​​：不支持的功能可以有回退方案

### 1. Capabilities 位掩码定义

```python
class Capabilities(IntFlag):
    """能力标志位掩码定义"""
    
    # 基础功能
    BASIC_PROTOCOL = 0x0001      # 基础协议支持
    AUTHENTICATION = 0x0002      # 认证支持
    HEARTBEAT = 0x0004           # 心跳机制支持
    
    # 高级功能
    COMPRESSION = 0x0008         # 数据压缩支持
    ENCRYPTION = 0x0010          # 数据加密支持
    MULTI_STREAM = 0x0020        # 多流支持
    
    # 节点管理功能
    NODE_DISCOVERY = 0x0040      # 节点发现
    LOAD_BALANCING = 0x0080      # 负载均衡
    FAILOVER = 0x0100            # 故障转移
    
    # 数据特性
    BINARY_DATA = 0x0200         # 二进制数据传输
    LARGE_PACKETS = 0x0400       # 大数据包支持
    STREAMING = 0x0800           # 流式数据传输
    
    # 监控和诊断
    METRICS = 0x1000             # 性能指标收集
    DIAGNOSTICS = 0x2000         # 诊断功能
    LOGGING = 0x4000             # 远程日志
    
    # 预留位
    RESERVED_1 = 0x8000          # 预留位1
    RESERVED_2 = 0x10000         # 预留位2
    
    # 组合能力
    STANDARD_CAPABILITIES = BASIC_PROTOCOL | AUTHENTICATION | HEARTBEAT
    ADVANCED_CAPABILITIES = STANDARD_CAPABILITIES | COMPRESSION | ENCRYPTION
    ENTERPRISE_CAPABILITIES = ADVANCED_CAPABILITIES | MULTI_STREAM | LOAD_BALANCING | FAILOVER
```

### 2. Capabilities 协商流程

#### 2.2 握手阶段的能力交换
```python
async def perform_handshake(self):
    """执行握手和能力协商"""
    # 客户端发送能力标志
    client_capabilities = (
        Capabilities.BASIC_PROTOCOL |
        Capabilities.AUTHENTICATION |
        Capabilities.HEARTBEAT |
        Capabilities.COMPRESSION
    )
    
    handshake_data = self.pack_handshake_request(
        version=1,
        protocol_version=1,
        identifier=self.worker_id,
        capabilities=client_capabilities
    )
    
    await self.send_packet(PacketType.HANDSHAKE_REQUEST, handshake_data)
    
    # 接收服务器响应
    response = await self.receive_packet(PacketType.HANDSHAKE_RESPONSE)
    server_capabilities = response['capabilities']
    
    # 协商共同支持的能力
    negotiated_capabilities = client_capabilities & server_capabilities
    self.logger.info(f"协商后的能力: {negotiated_capabilities}")
    
    return negotiated_capabilities
```

#### 2.2 能力检查方法
```python
def check_capability(self, capability: Capabilities) -> bool:
    """检查是否支持特定能力"""
    return (self.negotiated_capabilities & capability) == capability

def require_capability(self, capability: Capabilities):
    """要求特定能力，如果不支持则抛出异常"""
    if not self.check_capability(capability):
        raise CapabilityNotSupportedError(
            f"所需能力不支持: {capability.name}, "
            f"当前能力: {self.negotiated_capabilities}"
        )
```

### 3. 能力相关的数据包格式

#### 3.1 握手请求中的能力字段

​​格式​​：版本(1B) | 协议版本(1B) | ID长度(1B) | ID(变长) | **能力标志(4B)**
```python
def pack_handshake_request(version: int, protocol_version: int, 
                          identifier: str, capabilities: int) -> bytes:
    """打包握手请求（包含能力标志）"""
    identifier_bytes = identifier.encode('utf-8')
    body_data = struct.pack('!BBB', version, protocol_version, len(identifier_bytes))
    body_data += identifier_bytes
    body_data += struct.pack('!I', capabilities)  # 4字节能力标志
    return body_data

def unpack_handshake_request(data: bytes) -> tuple:
    """解包握手请求（包含能力标志）"""
    version, protocol_version, id_length = struct.unpack('!BBB', data[:3])
    identifier = data[3:3+id_length].decode('utf-8')
    capabilities = struct.unpack('!I', data[3+id_length:7+id_length])[0]
    return version, protocol_version, identifier, capabilities
```

#### 3.2 握手响应中的能力字段

​​格式​​：状态(1B) | 服务器版本(1B) | **支持的能力(4B)**

```python
def pack_handshake_response(status: int, server_version: int, 
                           supported_capabilities: int) -> bytes:
    """打包握手响应（包含能力标志）"""
    return struct.pack('!BBI', status, server_version, supported_capabilities)

def unpack_handshake_response(data: bytes) -> tuple:
    """解包握手响应（包含能力标志）"""
    return struct.unpack('!BBI', data)
```

### 4. 能力使用示例

#### 4.1 基于能力的路由

```python
async def handle_packet(self, packet_type: int, data: bytes):
    """根据能力处理数据包"""
    if packet_type == PacketType.REQUEST_NODE:
        if self.check_capability(Capabilities.LOAD_BALANCING):
            await self.handle_load_balanced_request(data)
        else:
            await self.handle_basic_request(data)
    
    elif packet_type == PacketType.DATA_TRANSFER:
        if self.check_capability(Capabilities.COMPRESSION):
            data = self.decompress_data(data)
        if self.check_capability(Capabilities.ENCRYPTION):
            data = self.decrypt_data(data)
        
        await self.process_data(data)
```

#### 4.2 能力依赖检查
```python
class CompressionPlugin(PluginBase):
    """压缩插件（需要压缩能力）"""
    
    async def handle_event(self, event: PluginEvent):
        if event.event_type == PluginEventType.DATA_SENDING:
            # 检查压缩能力
            if not self.plugin_manager.check_capability(Capabilities.COMPRESSION):
                return event.data  # 不支持压缩，直接返回原数据
            
            # 支持压缩，进行压缩处理
            compressed_data = self.compress_data(event.data)
            return compressed_data
```

### 5. 能力版本管理

#### 5.1 能力与版本映射

```python
CAPABILITY_VERSIONS = {
    # 能力标志: 引入版本
    Capabilities.BASIC_PROTOCOL: "1.0.0",
    Capabilities.AUTHENTICATION: "1.0.0",
    Capabilities.HEARTBEAT: "1.1.0",
    Capabilities.COMPRESSION: "1.2.0",
    Capabilities.ENCRYPTION: "1.3.0",
    Capabilities.MULTI_STREAM: "2.0.0",
    Capabilities.LOAD_BALANCING: "2.1.0",
}

def get_capabilities_for_version(version: str) -> int:
    """获取指定版本支持的能力"""
    capabilities = 0
    for cap, intro_version in CAPABILITY_VERSIONS.items():
        if version >= intro_version:
            capabilities |= cap
    return capabilities
```

#### 5.2 向后兼容性处理
```python
async def handle_legacy_client(self, client_capabilities: int):
    """处理旧版本客户端"""
    # 获取当前服务器支持的所有能力
    server_capabilities = self.get_server_capabilities()
    
    # 过滤掉客户端不支持的能力
    compatible_capabilities = server_capabilities & client_capabilities
    
    # 对于不支持的能力，使用回退方案
    if not (compatible_capabilities & Capabilities.COMPRESSION):
        self.logger.warning("客户端不支持压缩，使用未压缩数据传输")
        self.disable_compression()
    
    if not (compatible_capabilities & Capabilities.ENCRYPTION):
        self.logger.warning("客户端不支持加密，使用明文传输")
        self.disable_encryption()
    
    return compatible_capabilities
```

### 6. 能力测试和验证

#### 6.1 能力测试套件
```python
class CapabilityTests(unittest.TestCase):
    """能力测试用例"""
    
    def test_capability_negotiation(self):
        """测试能力协商"""
        client_caps = Capabilities.BASIC_PROTOCOL | Capabilities.AUTHENTICATION
        server_caps = Capabilities.BASIC_PROTOCOL | Capabilities.HEARTBEAT
        
        negotiated = client_caps & server_caps
        self.assertEqual(negotiated, Capabilities.BASIC_PROTOCOL)
        self.assertTrue(negotiated & Capabilities.BASIC_PROTOCOL)
        self.assertFalse(negotiated & Capabilities.AUTHENTICATION)
    
    def test_capability_checking(self):
        """测试能力检查"""
        caps = Capabilities.BASIC_PROTOCOL | Capabilities.AUTHENTICATION
        
        # 检查支持的能力
        self.assertTrue(caps & Capabilities.BASIC_PROTOCOL)
        self.assertTrue(caps & Capabilities.AUTHENTICATION)
        
        # 检查不支持的能力
        self.assertFalse(caps & Capabilities.HEARTBEAT)
        self.assertFalse(caps & Capabilities.COMPRESSION)
```

### 7. 错误处理

#### 7.1 能力相关异常
```python
class CapabilityError(Exception):
    """能力相关异常基类"""
    pass

class CapabilityNotSupportedError(CapabilityError):
    """能力不支持异常"""
    def __init__(self, capability, supported_capabilities):
        self.capability = capability
        self.supported_capabilities = supported_capabilities
        message = f"能力不支持: {capability}, 支持的能力: {supported_capabilities}"
        super().__init__(message)

class CapabilityNegotiationFailedError(CapabilityError):
    """能力协商失败异常"""
    pass
```

#### 7.2 能力错误处理
```python
async def handle_capability_error(self, error: CapabilityError):
    """处理能力错误"""
    if isinstance(error, CapabilityNotSupportedError):
        self.logger.warning(f"能力不支持: {error.capability}")
        
        # 发送能力错误事件
        error_event = PluginEvent(
            PluginEventType.CAPABILITY_ERROR,
            self,
            {
                'error_type': 'capability_not_supported',
                'capability': error.capability,
                'supported_capabilities': error.supported_capabilities
            }
        )
        await self.emit_event(error_event)
        
        # 根据错误类型采取不同的回退策略
        if error.capability == Capabilities.COMPRESSION:
            await self.fallback_to_uncompressed()
        elif error.capability == Capabilities.ENCRYPTION:
            await self.fallback_to_unencrypted()
```


## 附录B：标准格式字符说明

​**​附录B**​​ 是指本技术文档的补充材料部分，专门解释 Python struct模块中使用的格式字符的含义和用法。这些格式字符用于定义二进
制数据的结构和字节顺序。

**格式字符表**

|格式字符|类型|大小 (字节)|说明|
|-|-|-|-|
|B|unsigned char|1|无符号字节|
|H|unsigned short|2|无符号短整型|
|I|unsigned int|4|无符号整型|
|Q|unsigned long long|8|无符号长长整型|
|s|char[]|1 * n|字符数组（需指定长度）|
|!|-|-|网络字节序（大端序）|

**格式字符组合示例**

|格式字符串|说明|示例数据|打包结果大小|
|-|-|-|-|
|!B|1字节无符号整数|255|1字节|
|!H|2字节无符号短整数|65535|2字节|
|!I|4字节无符号整数|4294967295|4字节|
|!Q|8字节无符号长整数|18446744073709551615|8字节|
|!BH|1字节整数 + 2字节短整数|(1, 65535)|3字节|
|!HHB|2字节短整数 + 2字节短整数 + 1字节整数|(1, 2, 3)|5字节|
|!BBB|3字节整数|(1, 2, 3)|3字节|
|!5s|5字节字符串|b"hello"|5字节|

**字节序说明**

|字符|字节序|说明|
|-|-|-|
|!|网络字节序|大端序，用于网络通信|
|>|大端序|与网络字节序相同|
|<|小端序|与主机字节序相同（x86架构）|
|=|本机字节序|使用本机字节序|

使用示例
```python
import struct

# 打包示例
packed_data = struct.pack('!HHB', 8080, 100, 15)
# 结果: b'\x1f\x90\x00d\x0f'

# 解包示例
port, capacity, capabilities = struct.unpack('!HHB', packed_data)
# 结果: (8080, 100, 15)
```

## 附录C：常用工具方法

​​**附录C​​** 提供了一组常用的工具方法，用于简化二进制数据的打包和解包操作。这些方法封装了 struct模块的功能，提供了更直观的接口。

打包方法 更多参考 `src/network/protocol.py`

```python
def pack_header(packet_type: int, length: int) -> bytes:
    """打包数据包头"""
    return struct.pack('!BH', packet_type, length)

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
...
```

解包方法 更多参考 `src/network/protocol.py`
```python
def unpack_header(data: bytes) -> tuple:
    """解包数据包头"""
    return struct.unpack('!BH', data)

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
...
```

使用示例
```python
# 使用工具方法打包数据
port = 8080
capacity = 100
capabilities = 15

packed_data = pack_hhb(port, capacity, capabilities)
# 结果: b'\x1f\x90\x00d\x0f'

# 使用工具方法解包数据
port_unpacked, capacity_unpacked, capabilities_unpacked = unpack_hhb(packed_data)
# 结果: (8080, 100, 15)
```

## 术语表

* ​**​大端序 (Big-Endian)​​：** 高位字节存储在低地址的字节序，网络通信标准字节序
* **​​小端序 (Little-Endian)​​：** 低位字节存储在低地址的字节序，x86架构主机字节序
* **​​数据包 (Packet)​​：** 网络通信中的基本数据传输单位
* **​​握手 (Handshake)​​：** 连接建立初期的协议协商过程
* ​**​认证 (Authentication)​​：** 验证身份的过程
* ​**​心跳 (Heartbeat)​​：** 定期发送的小数据包，用于维持连接和检测存活状态
* **​​插件 (Plugin)​​：** 可扩展系统功能的模块化组件
* **​​节点 (Node)​​：** 网络中的一个参与实体，可以是服务器或客户端

## 常见问题解答

**Q: 为什么使用网络字节序（大端序）？**

A: 网络字节序是网络通信的标准字节序，确保不同架构的设备能够正确解析数据。

**Q: 如何处理变长数据？**

A: 变长数据通常采用"长度+数据"的格式，先发送数据长度，再发送实际数据。

**Q: 插件系统如何工作？**

A: 插件系统通过事件驱动机制工作，插件可以监听特定事件并执行相应操作。

**Q: 如何添加新的数据包类型？**

A: 在 PacketType枚举中添加新类型，实现相应的打包和解包方法，并更新文档。

**Q: 如何处理版本兼容性？**

A: 协议设计应支持向后兼容，新版本协议应能处理旧版本客户端的请求。

----

文档版本：1.0.2​​

​​最后更新：2025-10-17 15:57:00
​