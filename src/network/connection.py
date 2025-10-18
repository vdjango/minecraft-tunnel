import asyncio
import logging
import struct
import time
import uuid

from typing import Any, Dict, List, Optional,Any

from core.plugin.manager import PluginManager
from core.plugin.types import PluginNodeType, PluginEvent, PluginEventType
from network.base import Connection, ConnectionBase

from .exceptions import ConnectionClosedError, HandshakeError
from .protocol import ActionType, PacketType, ConnectionState, pack_byte, pack_byte_byte, pack_header, pack_ulonglong, pack_ushort, unpack_byte, unpack_byte_byte_byte, unpack_header, unpack_ulonglong, unpack_ushort


from typing import Dict, Any, List, Optional, Set, Callable
from dataclasses import dataclass
from .protocol import PacketType, ActionType



class ConnectionManager(ConnectionBase):
    """连接管理器，统一处理网络IO"""
    
    def __init__(self, config: Dict, plugin_manager: PluginManager):
        self.config = config
        self.plugin_manager = plugin_manager
        self.logger = logging.getLogger("ConnectionManager")
        self.connections: Dict[str, Connection] = {}
        self._running = False
        self._read_tasks: Set[asyncio.Task] = set()
        self._monitor_task: Optional[asyncio.Task] = None
        self._server: Optional[asyncio.Server] = None
    
    async def start(self):
        """启动连接管理器"""
        await super(ConnectionManager, self).start()
        # 启动连接监控任务
        self._monitor_task = asyncio.create_task(self._monitor_connections())

    async def stop(self):
        """停止连接管理器"""
        if self._monitor_task and not self._monitor_task.done():
            # 取消监控任务
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        await super(ConnectionManager, self).stop()

    async def process_packet(self, connection: Connection, packet_type: int, data: bytes):
        """处理数据包"""
        try:
            # 发送数据包接收事件
            await self.plugin_manager.emit_event(PluginEvent(
                PluginEventType.PACKET_RECEIVED,
                self,
                {
                    'connection_id': connection.connection_id,
                    'client_addr': connection.client_addr,
                    'packet_type': packet_type,
                    'data': data
                }
            ))
            
            # 根据数据包类型处理
            if packet_type == PacketType.HEARTBEAT:  # 心跳包
                result: list = await self.plugin_manager.execute_action_plugins('heartbeat', {
                    'connection': connection,
                    'data': data,
                    'connection_id': connection.connection_id,
                    'client_addr': connection.client_addr
                })
                plugin_response = result[0] if result else None
                await self._send_plugin_response(connection, plugin_response)
            elif packet_type == PacketType.REGISTER_NODE:  # 注册节点
                result: list = await self.plugin_manager.execute_action_plugins('registration', {
                    'connection': connection,
                    'data': data,
                    'connection_id': connection.connection_id,
                    'client_addr': connection.client_addr
                })
                plugin_response = result[0] if result else None
                await self._send_plugin_response(connection, plugin_response)
            elif packet_type == PacketType.REQUEST_NODE:  # 请求节点
                result: list = await self.plugin_manager.execute_action_plugins('request_node', {
                    'connection': connection,
                    'data': data,
                    'connection_id': connection.connection_id,
                    'client_addr': connection.client_addr
                })
                plugin_response = result[0] if result else None
                await self._send_plugin_response(connection, plugin_response)
            elif packet_type == PacketType.STATUS_UPDATE:  # 状态更新
                result: list = await self.plugin_manager.execute_action_plugins('status_update', {
                    'connection': connection,
                    'data': data,
                    'connection_id': connection.connection_id,
                    'client_addr': connection.client_addr
                })
                plugin_response = result[0] if result else None
                await self._send_plugin_response(connection, plugin_response)
            elif packet_type == PacketType.DISCONNECT:  # 断开连接
                result: list = await self.plugin_manager.execute_action_plugins('disconnect', {
                    'connection': connection,
                    'data': data,
                    'connection_id': connection.connection_id,
                    'client_addr': connection.client_addr
                })
                plugin_response = result[0] if result else None
                await self._send_plugin_response(connection, plugin_response)
                await self._handle_disconnect(connection, data)
            elif packet_type == PacketType.HANDSHAKE_REQUEST:  # 握手请求
                result: list = await self.plugin_manager.execute_action_plugins('handshake', {
                    'connection': connection,
                    'data': data,
                    'connection_id': connection.connection_id,
                    'client_addr': connection.client_addr
                })
                plugin_response = result[0] if result else None
                await self._send_plugin_response(connection, plugin_response)
                # 注意：握手请求通常在握手阶段处理，这里可能不会出现，但为了完整性可以处理或记录
                self.logger.warning(f"[非法操作] 处于就绪状态的意外握手请求: {connection.connection_id}")
            elif packet_type == PacketType.AUTH_REQUEST:  # 认证请求
                result: list = await self.plugin_manager.execute_action_plugins('authentication', {
                    'connection': connection,
                    'data': data,
                    'connection_id': connection.connection_id,
                    'client_addr': connection.client_addr
                })
                plugin_response = result[0] if result else None
                await self._send_plugin_response(connection, plugin_response)
            else:
                result: list = await self.plugin_manager.execute_action_plugins('custom', {
                    'connection': connection,
                    'data': data,
                    'connection_id': connection.connection_id,
                    'client_addr': connection.client_addr
                })
                plugin_response = result[0] if result else None
                await self._send_plugin_response(connection, plugin_response)

                self.logger.warning(f"未知数据包类型: {packet_type}, Connection: {connection.connection_id}")
                await self.plugin_manager.emit_event(PluginEvent(
                    PluginEventType.CUSTOM_EVENT,
                    self,
                    {
                        'connection_id': connection.connection_id,
                        'client_addr': connection.client_addr,
                        'event_type': 'unknown_packet',
                        'packet_type': packet_type,
                        'data': data
                    }
                ))
            
            # 发送数据包处理完成事件
            await self.plugin_manager.emit_event(PluginEvent(
                PluginEventType.PACKET_PROCESSED,
                self,
                {
                    'connection_id': connection.connection_id,
                    'client_addr': connection.client_addr,
                    'packet_type': packet_type,
                    'data': data
                }
            ))
            
        except Exception as e:
            self.logger.error(f"处理数据包时出错: {connection.connection_id}, Error: {e}")
            import traceback
            traceback.print_exc()
            # 发送数据包处理错误事件
            await self.plugin_manager.emit_event(PluginEvent(
                PluginEventType.CONNECTION_ERROR,
                self,
                {
                    'connection_id': connection.connection_id,
                    'client_addr': connection.client_addr,
                    'error': f"Packet processing error: {e}",
                    'packet_type': packet_type
                }
            ))
    
    async def _handle_disconnect(self, connection: Connection, data: bytes):
        """处理断开连接请求（修复版）""" # TODO 做成插件
        try:
            # 解析断开连接数据
            # 格式: 原因长度(2B) | 原因(变长)
            if len(data) < 2:
                reason = "Unknown reason"
            else:
                reason_length = unpack_ushort(data[:2])
                if len(data) < 2 + reason_length:
                    reason = "Invalid reason format"
                else:
                    reason = data[2:2+reason_length].decode('utf-8')
            
            # 发送断开连接响应
            # 格式: 状态(1B) | 消息长度(2B) | 消息(变长)
            message = "Disconnect acknowledged".encode('utf-8')
            response_data = pack_header(0x00, len(message)) + message
            await self._send_data(connection, response_data, PacketType.DISCONNECT)
            
            # 发送断开连接事件
            await self.plugin_manager.emit_event(PluginEvent(
                PluginEventType.CONNECTION_CLOSED,
                self,
                {
                    'connection_id': connection.connection_id,
                    'client_addr': connection.client_addr,
                    'state': connection.state.value,
                    'disconnect_data': {
                        'reason': reason
                    }
                }
            ))
            
            # 关闭连接
            await self.close_connection(connection.connection_id)
            
        except Exception as e:
            import traceback
            traceback.print_exc()

            self.logger.error(f"处理断开连接时出错: {connection.connection_id}, Error: {e}")
            # 即使出错也要关闭连接
            await self.close_connection(connection.connection_id)

    async def _monitor_connections(self):
        """监控连接状态"""
        while self._running:
            try:
                # 检查所有连接的活动状态
                inactive_connections = []
                current_time = time.time()
                
                for connection_id, connection in list(self.connections.items()):
                    # 检查连接是否超时
                    if not connection.is_active(timeout=300):  # 5分钟超时
                        self.logger.warning(f"连接超时: {connection_id}")
                        inactive_connections.append(connection_id)
                    # 检查连接是否长时间处于非就绪状态
                    elif (connection.state != ConnectionState.READY and 
                          current_time - connection.last_activity > 60):  # 1分钟
                        self.logger.warning(f"连接卡滞 {connection.state}: {connection_id}")
                        inactive_connections.append(connection_id)
                
                # 关闭不活跃的连接
                for connection_id in inactive_connections:
                    self.logger.info(f"关闭非活动连接: {connection_id}")
                    await self.close_connection(connection_id)
                
                # 记录连接统计
                active_count = len([c for c in self.connections.values() if c.is_active()])
                ready_count = len([c for c in self.connections.values() if c.is_ready()])
                self.logger.info(f"Connection stats: {active_count} active, {ready_count} ready, {len(self.connections)} total")
                
                # 等待下一次检查
                await asyncio.sleep(30)  # 每30秒检查一次
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"连接监视器出错: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(10)  # 出错时等待10秒


# 连接管理器工厂函数
def create_connection_manager(config: Dict, plugin_manager: PluginManager) -> ConnectionManager:
    """创建连接管理器实例"""
    return ConnectionManager(config, plugin_manager)

# 连接管理器单例模式
class ConnectionManagerSingleton:
    """连接管理器单例"""
    _instance = None
    
    @classmethod
    def get_instance(cls, config: Dict, plugin_manager: PluginManager) -> ConnectionManager:
        """获取连接管理器单例"""
        if cls._instance is None:
            cls._instance = ConnectionManager(config, plugin_manager)
        return cls._instance
    
    @classmethod
    def destroy_instance(cls):
        """销毁连接管理器单例"""
        if cls._instance:
            cls._instance = None
