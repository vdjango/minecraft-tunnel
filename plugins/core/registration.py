import struct
import logging
import time
import asyncio
from typing import Dict, Any, Optional, List, Union
from core.plugin.base import ActionPlugin
from core.plugin.types import PluginEvent, PluginEventType, PluginPriority, PluginNodeType
from discovery.models import NodeInfo
from network.protocol import pack_byte_ushort, unpack_byte, unpack_ushort
from discovery.registry import ServiceRegistry


logger = logging.getLogger("RegistrationPlugin")


class RegistrationPlugin(ActionPlugin):
    """注册插件，处理Worker节点向Master的注册请求"""
    
    PLUGIN_NAME = "注册插件"
    PLUGIN_VERSION = "1.0.0"
    PLUGIN_DESCRIPTION = "处理Worker节点向Master服务器的注册请求"
    PLUGIN_AUTHOR = "系统"
    ACTION_TYPE = "registration"  # 注意：这里使用 register_node 而不是 registration
    PLUGIN_PRIORITY = PluginPriority.HIGHEST
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.registry: ServiceRegistry = self.plugin_manager.registry  # 已注册的Worker节点
        self.worker_capabilities = {}  # Worker能力信息
        self.last_heartbeat = {}      # 最后心跳时间
    
    async def handle_action(self, connection, data: bytes, context: Dict) -> Any:
        """处理Worker注册请求"""
        try:
            # 解析注册请求数据
            # 格式: 节点类型(1B) | 主机长度(1B) | 主机(变长) | 端口(2B) | 容量(2B) | 能力标志(1B)
            if len(data) < 1:
                return self._create_error_response("无效的注册数据格式")
            
            # 解析节点类型
            node_type = unpack_byte(data[0:1])
            
            # 验证节点类型
            if node_type not in [t.value for t in PluginNodeType]:
                return self._create_error_response(f"无效的节点类型: {node_type}")
            
            # 解析主机信息
            if len(data) < 2:
                return self._create_error_response("无效的主机长度")
            
            host_length = unpack_byte(data[1:2])
            if len(data) < 2 + host_length + 5:  # 主机长度 + 端口(2) + 容量(2) + 能力(1)
                return self._create_error_response("数据长度不足")
            
            host = data[2:2+host_length].decode('utf-8')
            
            # 解析端口、容量和能力标志
            port_data = data[2+host_length:2+host_length+2]
            capacity_data = data[2+host_length+2:2+host_length+4]
            capabilities_data = data[2+host_length+4:2+host_length+5]
            
            port = unpack_ushort(port_data)
            capacity = unpack_ushort(capacity_data)
            capabilities = unpack_byte(capabilities_data)
            
            # 获取连接信息
            connection_id = context.get('connection_id')
            client_addr = context.get('client_addr')
            worker_id = getattr(connection, 'worker_id', None) or f"worker_{connection_id}"
            
            # 注册Worker节点
            success, message = await self.register_worker(
                connection_id=connection_id,
                worker_id=worker_id,
                node_type=node_type,
                host=host,
                port=port,
                capacity=capacity,
                capabilities=capabilities,
                client_addr=client_addr
            )
            
            # 构造响应
            if success:
                response_data = self._create_success_response(message)
                logger.info(f"节点注册成功: {worker_id} ({PluginNodeType(node_type).name})")
            else:
                response_data = self._create_error_response(message)
                logger.warning(f"节点注册失败: {worker_id}, 原因: {message}")
            
            # 返回单个结果，而不是列表
            return {
                'success': success,
                'type': 0x05,  # REGISTER_NODE_RESPONSE
                'data': response_data
            }
            
        except Exception as e:
            logger.error(f"注册处理错误: {e}")
            return self._create_error_response(f"注册处理错误: {e}")
    
    async def register_worker(self, connection_id: str, worker_id: str, node_type: int, 
                            host: str, port: int, capacity: int, capabilities: int, 
                            client_addr: Any) -> tuple:
        """注册Worker节点到Master"""
        try:
            # 检查Worker是否已注册
            if await self.plugin_manager.registry.get_node(worker_id):
                return False, "Worker已注册"
            
            # 验证Worker信息
            if not self._validate_worker_info(node_type, host, port, capacity):
                return False, "Worker信息无效"

            await self.registry.register_node(NodeInfo(**{
                'host': host,
                'port': port,
                'node_id': worker_id,
                'node_type': node_type,
                'capacity': capacity,
                'capabilities': capabilities,   # # 节点能力描述
                'last_heartbeat': time.time(),
                'load': 0.0  # 初始负载为0
            }))

            # 保存Worker信息
            self.worker_capabilities[worker_id] = capabilities
            self.last_heartbeat[worker_id] = time.time()
            
            # 发送Worker注册事件
            await self.plugin_manager.emit_event(PluginEvent(
                PluginEventType.NODE_REGISTER,
                self,
                {
                    'last_timedate': time.time()
                }
            ))
            return True, "Worker注册成功"
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"注册Worker错误: {e}")
            return False, f"注册失败: {str(e)}"
    
    def _validate_worker_info(self, node_type: int, host: str, port: int, capacity: int) -> bool:
        """验证Worker信息有效性"""
        # 检查主机格式
        if not host or len(host) > 255:
            return False
        
        # 检查端口范围
        if port < 1 or port > 65535:
            return False
        
        # 检查容量
        if capacity < 0 or capacity > 65535:
            return False
        
        # 检查节点类型
        if node_type not in [t.value for t in PluginNodeType]:
            return False
        
        return True
    
    def _create_success_response(self, message: str) -> bytes:
        """创建成功响应"""
        message_bytes = message.encode('utf-8')
        # 响应格式: 状态(1B) | 消息长度(2B) | 消息(变长)
        return pack_byte_ushort(0x00, len(message_bytes)) + message_bytes
    
    def _create_error_response(self, error_message: str) -> bytes:
        """创建错误响应"""
        message_bytes = error_message.encode('utf-8')
        # 响应格式: 状态(1B) | 消息长度(2B) | 消息(变长)
        return pack_byte_ushort(0x01, len(message_bytes)) + message_bytes
    
    async def on_load(self, event: PluginEvent):
        """插件加载时调用"""
        logger.info("注册插件已加载")
    
    async def on_init(self, event: PluginEvent):
        """插件初始化时调用"""
        logger.info("注册插件已初始化")
    
    async def on_enable(self, event: PluginEvent):
        """插件启用时调用"""
        logger.info("注册插件已启用")
    
    async def on_disable(self, event: PluginEvent):
        """插件禁用时调用"""
        logger.info("注册插件已禁用")
