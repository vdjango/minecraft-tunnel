import logging
import time
from typing import Dict
from core.plugin.base import ActionPlugin
from core.plugin.types import PluginEvent, PluginEventType, PluginPriority
from network.protocol import PacketType, pack_header, pack_ulonglong, unpack_ulonglong


class HeartbeatPlugin(ActionPlugin):
    """心跳处理插件"""
    
    PLUGIN_NAME = "心跳插件"
    PLUGIN_VERSION = "1.0.0"
    PLUGIN_DESCRIPTION = "处理心跳请求并发送响应"
    PLUGIN_AUTHOR = "系统"
    ACTION_TYPE = "heartbeat"
    PLUGIN_PRIORITY = PluginPriority.HIGH
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger("HeartbeatPlugin")
    
    async def handle_action(self, connection, data: bytes, context: Dict) -> Dict:
        """处理心跳请求"""
        try:
            # 解析心跳数据
            if len(data) < 8:
                raise ValueError("无效的心跳数据长度")
            
            # 解包时间戳
            timestamp = unpack_ulonglong(data[:8])
            current_time = int(time.time() * 1000)
            latency = current_time - timestamp
            
            # 更新连接活动时间
            connection.update_activity()
            
            # 创建心跳响应
            response_data = pack_ulonglong(current_time)
            
            # 发送心跳事件
            await self.plugin_manager.emit_event(PluginEvent(
                PluginEventType.HEARTBEAT,
                self,
                {
                    'connection_id': context['connection_id'],
                    'client_addr': context['client_addr'],
                    'timestamp': timestamp,
                    'latency': latency,
                    'current_time': current_time
                }
            ))
            
            return {
                'response_type': PacketType.HEARTBEAT,
                'data': response_data
            }
            
        except Exception as e:
            self.logger.error(f"心跳处理错误: {e}")
            
            # 创建错误响应
            error_msg = f"心跳处理错误: {e}".encode('utf-8')
            error_response = pack_header(0x01, len(error_msg)) + error_msg
            
            return {
                'response_type': PacketType.HEARTBEAT,
                'data': error_response
            }
