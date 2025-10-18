import struct
import logging
import asyncio
from typing import Dict, Any, Optional
from core.plugin.base import ActionPlugin
from core.plugin.types import PluginEvent, PluginEventType, PluginPriority, PluginNodeType
from discovery.models import NodeInfo
from network.protocol import PacketType, pack_byte, pack_ushort, unpack_byte, unpack_ushort

logger = logging.getLogger("NodeRequestPlugin")


class NodeRequestPlugin(ActionPlugin):
    """节点请求处理插件，处理客户端节点分配请求"""
    
    PLUGIN_NAME = "节点请求插件"
    PLUGIN_VERSION = "1.0.0"
    PLUGIN_DESCRIPTION = "处理客户端节点分配请求并返回合适的节点"
    PLUGIN_AUTHOR = "系统"
    ACTION_TYPE = "request_node"  # 动作类型
    PLUGIN_PRIORITY = PluginPriority.HIGHEST  # 最高优先级
    PLUGIN_NODE_TYPES = [PluginNodeType.MASTER]  # 在Master节点运行
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.registry = self.plugin_manager.registry  # 服务注册表
    
    async def handle_action(self, connection, data: bytes, context: Dict) -> Any:
        """处理节点请求"""
        try:
            # 解析请求数据
            # 格式: 客户端类型(1B) | 游戏版本长度(1B) | 游戏版本(变长) | 模组信息长度(2B) | 模组信息(变长)
            if len(data) < 1:
                return self._create_error_response("无效的请求数据格式")
            
            # 解析客户端类型
            client_type = unpack_byte(data[0:1])
            
            # 解析游戏版本
            if len(data) < 2:
                return self._create_error_response("无效的游戏版本长度")
            
            game_version_length = unpack_byte(data[1:2])
            if len(data) < 2 + game_version_length + 2:
                return self._create_error_response("数据长度不足")
            
            game_version = data[2:2+game_version_length].decode('utf-8')
            
            # 解析模组信息
            mods_info_length = unpack_ushort(data[2+game_version_length:4+game_version_length])
            if len(data) < 4 + game_version_length + mods_info_length:
                return self._create_error_response("模组信息长度不足")
            
            mods_info = data[4+game_version_length:4+game_version_length+mods_info_length].decode('utf-8')
            
            # 获取连接信息
            connection_id = context.get('connection_id')
            client_addr = context.get('client_addr')
            
            # 选择合适节点
            selected_node: NodeInfo = await self.registry.select_node()
            if not selected_node:
                return self._create_error_response("没有可用节点")
            
            # 构造成功响应
            response_data = self._create_node_response(selected_node)
            
            # 记录请求日志
            logger.info(f"节点分配成功: 客户端 {client_addr} -> 节点 {selected_node.node_id}")
            
            return {
                'success': True,
                'type': PacketType.REQUEST_NODE,  # REQUEST_NODE 响应
                'data': response_data
            }
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"节点请求处理错误: {e}")
            return self._create_error_response(f"节点请求处理错误: {e}")
    
    def _create_node_response(self, node_info: NodeInfo) -> bytes:
        """创建节点响应数据"""
        # 转换为字节
        node_id_bytes = node_info.node_id.encode('utf-8')
        host_bytes = node_info.host.encode('utf-8')
        
        # 构造响应数据
        # 格式: 状态(1B) | 节点ID长度(1B) | 节点ID(变长) | 主机长度(1B) | 主机(变长) | 端口(2B)
        response_data = pack_byte(0x00)  # 成功状态
        response_data += pack_byte(len(node_id_bytes))
        response_data += node_id_bytes
        response_data += pack_byte(len(host_bytes))
        response_data += host_bytes
        response_data += pack_ushort(node_info.port)
        return response_data
    
    def _create_error_response(self, error_message: str) -> Dict[str, Any]:
        """创建错误响应"""
        message_bytes = error_message.encode('utf-8')
        # 响应格式: 状态(1B) | 消息长度(2B) | 消息(变长)
        response_data = pack_byte(0x01)  # 错误状态
        response_data += pack_ushort(len(message_bytes))
        response_data += message_bytes
        
        return {
            'success': False,
            'type': PacketType.REQUEST_NODE,  # REQUEST_NODE 响应
            'data': response_data
        }
    
    async def on_load(self, event: PluginEvent):
        """插件加载时调用"""
        logger.info("节点请求插件已加载")
    
    async def on_init(self, event: PluginEvent):
        """插件初始化时调用"""
        logger.info("节点请求插件已初始化")
    
    async def on_enable(self, event: PluginEvent):
        """插件启用时调用"""
        logger.info("节点请求插件已启用")
    
    async def on_disable(self, event: PluginEvent):
        """插件禁用时调用"""
        logger.info("节点请求插件已禁用")
