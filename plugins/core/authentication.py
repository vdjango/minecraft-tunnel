import struct
import logging
from typing import Dict, Any, Optional
from core.plugin.base import ActionPlugin
from core.plugin.types import PluginEvent, PluginEventType, PluginPriority
from network.protocol import PacketType, pack_header, unpack_header

logger = logging.getLogger("AuthPlugin")


class AuthenticationPlugin(ActionPlugin):
    """认证插件，处理客户端认证请求"""
    
    PLUGIN_NAME = "认证插件"
    PLUGIN_VERSION = "1.0.0"
    PLUGIN_DESCRIPTION = "处理客户端认证请求"
    PLUGIN_AUTHOR = "系统"
    ACTION_TYPE = "authentication"
    PLUGIN_PRIORITY = PluginPriority.CRITICAL  # 设置为高优先级
    
    def __init__(self, *agrs, **kwargs):
        super().__init__(*agrs, **kwargs)
        self.auth_key = b'secure_auth_key'
    
    async def handle_action(self, connection, data: bytes, context: Dict) -> Any:
        """处理认证动作"""
        try:
            # 解析认证请求数据
            # 格式: 认证类型(1B) | 凭证长度(2B) | 凭证数据(变长)
            if len(data) < 3:
                return self._create_error_response("无效的认证数据格式")
            
            auth_type, cred_length = unpack_header(data[:3])
            if len(data) < 3 + cred_length:
                return self._create_error_response("无效的凭证长度")
            
            credential = data[3:3+cred_length]
            
            # 验证凭证
            is_authenticated = credential == self.auth_key
            
            # 构造认证响应
            if is_authenticated:
                message = "认证成功".encode('utf-8')
                response_data = pack_header(0x00, len(message)) + message
                logger.info(f"节点身份认证成功: {context.get('client_addr', '未知')}")
            else:
                message = "认证失败".encode('utf-8')
                response_data = pack_header(0x01, len(message)) + message
                logger.warning(f"节点认证失败: {context.get('client_addr', '未知')}")
            
            # 发送认证完成事件
            await self.plugin_manager.emit_event(PluginEvent(
                PluginEventType.CONNECTION_AUTHENTICATED,
                self,
                {
                    'connection_id': context.get('connection_id'),
                    'client_addr': context.get('client_addr'),
                    'authenticated': is_authenticated,
                    'auth_type': auth_type
                }
            ))
            return {
                'success': True,
                'type': PacketType.AUTH_RESPONSE,
                'data': response_data
            }
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"认证处理错误: {e}")
            return self._create_error_response(f"认证处理错误: {e}")
    
    def _create_error_response(self, error_message: str) -> Dict[str, Any]:
        """创建错误响应"""
        message = error_message.encode('utf-8')
        response_data = pack_header(0x01, len(message)) + message
        return {
            'success': False,
            'type': PacketType.AUTH_RESPONSE,
            'data': response_data
        }
    
    async def on_load(self, event: PluginEvent):
        """插件加载时调用"""
        logger.info("认证插件已加载")
    
    async def on_init(self, event: PluginEvent):
        """插件初始化时调用"""
        logger.info("认证插件已初始化")
    
    async def on_enable(self, event: PluginEvent):
        """插件启用时调用"""
        logger.info("认证插件已启用")
    
    async def on_disable(self, event: PluginEvent):
        """插件禁用时调用"""
        logger.info("认证插件已禁用")
