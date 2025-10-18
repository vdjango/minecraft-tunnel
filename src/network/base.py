from abc import ABC, abstractmethod
import asyncio
import logging
import struct
import time
import uuid

from typing import Any, Dict, List, Optional,Any

from core.plugin.manager import PluginManager
from core.plugin.types import PluginNodeType, PluginEvent, PluginEventType

from .exceptions import ConnectionClosedError, HandshakeError
from .protocol import ActionType, PacketType, ConnectionState, pack_byte, pack_byte_byte, pack_header, pack_ulonglong, pack_ushort, unpack_byte, unpack_byte_byte_byte, unpack_header, unpack_ulonglong, unpack_ushort


from typing import Dict, Any, List, Optional, Set, Callable
from dataclasses import dataclass
from .protocol import PacketType, ActionType


@dataclass
class Connection:
    """连接信息（修复版）"""
    connection_id: str
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    client_addr: tuple
    state: ConnectionState = ConnectionState.CONNECTED
    last_activity: float = None
    metadata: Dict = None
    worker_id: Optional[str] = None
    node_type: Optional[PluginNodeType] = None
    
    def __post_init__(self):
        if self.last_activity is None:
            self.last_activity = time.time()
        if self.metadata is None:
            self.metadata = {}
    
    def update_activity(self):
        """更新最后活动时间"""
        self.last_activity = time.time()
    
    def is_active(self, timeout: float = 300) -> bool:
        """检查连接是否活跃"""
        return time.time() - self.last_activity < timeout
    
    def is_ready(self) -> bool:
        """检查连接是否就绪"""
        return self.state == ConnectionState.READY
    
    def is_closed(self) -> bool:
        """检查连接是否已关闭"""
        return self.state in [ConnectionState.CLOSING, ConnectionState.CLOSED, ConnectionState.ERROR]
    
    def is_closing(self) -> bool:
        """检查连接是否正在关闭"""
        return self.state == ConnectionState.CLOSING
    
    def is_error(self) -> bool:
        """检查连接是否处于错误状态"""
        return self.state == ConnectionState.ERROR
    

class ConnectionBase:
    """连接管理器，统一处理网络IO"""
    
    def __init__(self, config: Dict, plugin_manager: PluginManager):
        self.config = config
        self._running = False
        self._server: Optional[asyncio.Server] = None
        self._read_tasks: Set[asyncio.Task] = set()
        self.plugin_manager = plugin_manager
        self.logger = logging.getLogger("ConnectionManager")
        self.connections: Dict[str, Connection] = {}
    
    @abstractmethod
    async def start_server(self):
        """启动服务器"""
        server_config = self.config.get('server', {})
        self._server = await asyncio.start_server(
            self.accept_connection,
            server_config.get('host', '0.0.0.0'),
            server_config.get('port', 3332),
            reuse_address=True,
            reuse_port=True,
            backlog=server_config.get('backlog', 1000)
        )
        server_addresses = ': '.join([str(sock.getsockname()) for sock in self._server.sockets])
        self.logger.info(f"服务器已启动 {server_addresses}")

    async def accept_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """接受新连接"""
        if not self._running:
            writer.close()
            await writer.wait_closed()
            return
        
        client_addr = writer.get_extra_info('peername')
        connection_id = str(uuid.uuid4())
        self.logger.info(f"建立新连接: {client_addr} (ID: {connection_id})")

        # 创建连接对象
        connection = Connection(
            connection_id=connection_id,
            reader=reader,
            writer=writer,
            client_addr=client_addr
        )
        
        # 添加到连接字典
        self.connections[connection_id] = connection
        
        # 发送连接接受事件
        await self.plugin_manager.emit_event(PluginEvent(
            PluginEventType.CONNECTION_ACCEPTED,
            self,
            {
                'connection_id': connection_id,
                'client_addr': client_addr,
                'state': connection.state
            }
        ))
        
        # 启动连接处理任务
        task = asyncio.create_task(self._handle_connection(connection))
        self._read_tasks.add(task)
        task.add_done_callback(lambda t: self._read_tasks.discard(t) if t in self._read_tasks else None)
    
    async def start(self):
        """启动连接管理器"""
        if self._running:
            return
        
        self._running = True
        await self.start_server()
    
    async def stop(self):
        """停止连接管理器"""
        if not self._running:
            return
        
        self._running = False

        # 取消所有读取任务
        for task in self._read_tasks:
            task.cancel()
        
        # 等待所有任务完成
        if self._read_tasks:
            await asyncio.gather(*self._read_tasks, return_exceptions=True)
        
        # 关闭所有连接
        for connection_id in list(self.connections.keys()):
            await self.close_connection(connection_id)
        
        # 关闭服务器
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    @abstractmethod
    async def process_packet(self):
        pass

    async def read_loop(self, connection: Connection):
        """数据读取循环"""
        while self._running and connection.is_ready():
            try:
                # 读取数据包头
                header = await asyncio.wait_for(
                    connection.reader.readexactly(3),
                    timeout=30.0
                )
                
                # 解析包头
                packet_type, data_length = unpack_header(header)
                
                # 读取数据
                data = await asyncio.wait_for(
                    connection.reader.readexactly(data_length),
                    timeout=30.0
                )
                
                # 更新活动时间
                connection.update_activity()
                
                # 发送数据接收事件
                await self.plugin_manager.emit_event(PluginEvent(
                    PluginEventType.CONNECTION_DATA_RECEIVED,
                    self,
                    {
                        'connection_id': connection.connection_id,
                        'client_addr': connection.client_addr,
                        'data': data,
                        'packet_type': packet_type,
                        'data_length': data_length
                    }
                ))

                # 处理数据包
                await self.process_packet(connection, packet_type, data)
                
            except asyncio.TimeoutError:
                # 超时是正常的，继续循环
                continue
            except asyncio.IncompleteReadError as e:
                self.logger.debug(f"客户端关闭的连接：{connection.connection_id}, 数据可能存在异常: {len(e.partial)} bytes")
                break
            except ConnectionResetError:
                self.logger.debug(f"客户端重置连接: {connection.connection_id}")
                break
            except Exception as e:
                import traceback
                traceback.print_exc()
                
                self.logger.error(f"读取数据时出错: {connection.connection_id}, Error: {e}")
                break

    async def _handle_connection(self, connection: Connection):
        """处理连接"""
        try:
            await self.plugin_manager.emit_event(PluginEvent(
                PluginEventType.CONNECTION_HANDSHAKE,
                self,
                {
                    'connection_id': connection.connection_id,
                    'client_addr': connection.client_addr,
                    'state': connection.state
                }
            ))

            # 握手阶段
            await self._handle_handshake(connection)
            
            # 连接就绪
            connection.state = ConnectionState.READY
            await self.plugin_manager.emit_event(PluginEvent(
                PluginEventType.CONNECTION_READY,
                self,
                {
                    'connection_id': connection.connection_id,
                    'client_addr': connection.client_addr,
                    'state': connection.state
                }
            ))
            
            # 进入数据读取循环
            await self.read_loop(connection)
            
        except asyncio.CancelledError:
            self.logger.debug(f"连接任务已取消: {connection.connection_id}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            self.logger.error(f"处理连接时出错 {connection.connection_id}: {e}")
            # 发送连接错误事件
            await self.plugin_manager.emit_event(PluginEvent(
                PluginEventType.CONNECTION_ERROR,
                self,
                {
                    'connection_id': connection.connection_id,
                    'client_addr': connection.client_addr,
                    'state': connection.state,
                    'error': str(e)
                }
            ))
        finally:
            # 关闭连接
            await self.close_connection(connection.connection_id)
    
    async def _handle_handshake(self, connection: Connection):
        """处理握手（带详细调试日志）"""
        connection.state = ConnectionState.HANDSHAKING
        
        try:
            # 读取握手数据
            header = await asyncio.wait_for(
                connection.reader.readexactly(3),
                timeout=30.0
            )
            version, protocol_version, id_length = unpack_byte_byte_byte(header)

            # 读取ID
            worker_id_bytes = await asyncio.wait_for(
                connection.reader.readexactly(id_length),
                timeout=30.0
            )
            worker_id = worker_id_bytes.decode('utf-8')
            
            # 读取能力标志（可选）
            capabilities = 0
            try:
                # 检查是否有更多数据
                if not connection.reader.at_eof():
                    # 尝试读取能力标志
                    capabilities_byte = await asyncio.wait_for(
                        connection.reader.readexactly(1),
                        timeout=1.0
                    )
                    capabilities = unpack_byte(capabilities_byte)  # [0]
                else:
                    self.logger.debug(f"未发送功能标志 {connection.connection_id}")
            except (asyncio.TimeoutError, asyncio.IncompleteReadError):
                self.logger.debug(f"客户端未发送功能标志，使用默认值: 0")
            except Exception as e:
                import traceback
                traceback.print_exc()
                
                self.logger.warning(f"读取功能标志错误: {e}")
            
            # 发送握手响应
            # 格式: 状态(1B) | 消息长度(2B) | 消息(变长) | 额外数据(变长)
            # 对于握手响应，消息为空，额外数据包含服务器版本和支持的能力
            status = 0x00  # 成功状态
            message_length = 0  # 消息长度为0
            server_version = 1
            supported_capabilities = 0x0F
            
            # 构造包体
            message_bytes = b""  # 空消息
            extra_data = pack_byte_byte(server_version, supported_capabilities)
            body_data = pack_header(status, message_length) + message_bytes + extra_data
            
            # 发送握手响应包
            await self._send_data(connection, body_data, PacketType.HANDSHAKE_RESPONSE)

            # 保存连接信息
            connection.worker_id = worker_id
            connection.metadata.update({
                'version': version,
                'protocol_version': protocol_version,
                'capabilities': capabilities
            })
            
            # 发送握手完成事件
            await self.plugin_manager.emit_event(PluginEvent(
                PluginEventType.CONNECTION_HANDSHAKE,
                self,
                {
                    'connection_id': connection.connection_id,
                    'client_addr': connection.client_addr,
                    'state': connection.state.value,
                    'handshake_data': {
                        'worker_id': worker_id,
                        'version': version,
                        'protocol_version': protocol_version,
                        'capabilities': capabilities
                    }
                }
            ))

        except asyncio.TimeoutError:
            self.logger.error(f"握手超时: {connection.connection_id}")
            raise Exception("握手超时")
        except Exception as e:
            import traceback
            traceback.print_exc()

            self.logger.error(f"握手错误: {connection.connection_id}, Error: {e}")
            raise
    
    async def _send_data(self, connection: Connection, data: bytes, packet_type: int = 0x00):
        """发送数据"""
        try:
            # 构建数据包
            # 格式: 类型(1B) | 长度(2B) | 数据(变长)
            packet_length = len(data)
            header = pack_header(packet_type, packet_length)
            packet = header + data
            
            # 发送数据
            connection.writer.write(packet)
            await connection.writer.drain()
            
            # 更新活动时间
            connection.update_activity()
            
            # 发送数据发送事件
            await self.plugin_manager.emit_event(PluginEvent(
                PluginEventType.CONNECTION_DATA_SENT,
                self,
                {
                    'connection_id': connection.connection_id,
                    'client_addr': connection.client_addr,
                    'data': data,
                    'packet_type': packet_type,
                    'data_length': packet_length
                }
            ))
        except Exception as e:
            import traceback
            traceback.print_exc()

            self.logger.error(f"发送数据时出错: {connection.connection_id}, Error: {e}")
            raise

    async def _send_plugin_response(self, connection: Connection, plugin_response: Dict):
        """发送插件响应"""
        if not plugin_response:
            # 插件未返回响应
            self.logger.warning("插件未返回响应")
            await self._send_system_error(connection, "无插件响应")
            return
        
        # 获取响应数据
        response_data = plugin_response.get('data')
        response_type = plugin_response.get('type', PacketType.REGISTER_NODE)
        
        # 发送响应
        if response_data:
            await self._send_data(connection, response_data, response_type)
        else:
            self.logger.warning("插件响应缺少数据")
            await self._send_system_error(connection, "插件响应无效")

    async def _send_system_error(self, connection: Connection, error_message: str):
        """发送系统级错误响应"""
        message_bytes = error_message.encode('utf-8')
        error_response = pack_header(0x01, len(message_bytes)) + message_bytes
        await self._send_data(connection, error_response, PacketType.REGISTER_NODE)
    
    async def close_connection(self, connection_id: str):
        """关闭连接"""
        if connection_id not in self.connections:
            return
        
        connection = self.connections[connection_id]
        client_addr = connection.client_addr

        # 如果连接已经关闭或正在关闭，直接返回
        if connection.is_closed() or connection.is_closing():
            return
        
        try:
            # 更新连接状态
            connection.state = ConnectionState.CLOSING
            
            # 发送连接关闭事件
            await self.plugin_manager.emit_event(PluginEvent(
                PluginEventType.CONNECTION_CLOSED,
                self,
                {
                    'connection_id': connection_id,
                    'client_addr': connection.client_addr,
                    'state': connection.state.value
                }
            ))
            
            # 关闭写入端
            if not connection.writer.is_closing():
                connection.writer.close()
                try:
                    await connection.writer.wait_closed()
                except Exception as e:
                    import traceback
                    traceback.print_exc()

                    self.logger.debug(f"等待写入程序关闭时出错: {e}")
            
            # 更新连接状态
            connection.state = ConnectionState.CLOSED
            
            # 从连接字典中移除
            del self.connections[connection_id]
            
            self.logger.info(f"连接已关闭: {client_addr} {connection_id}")
            
        except Exception as e:
            import traceback
            traceback.print_exc()

            self.logger.error(f"关闭连接时出错 {client_addr} {connection_id}: {e}")
            connection.state = ConnectionState.ERROR
            
            # 发送连接错误事件
            await self.plugin_manager.emit_event(PluginEvent(
                PluginEventType.CONNECTION_ERROR,
                self,
                {
                    'connection_id': connection_id,
                    'client_addr': connection.client_addr,
                    'state': connection.state.value,
                    'error': f"关闭连接时出错: {e}"
                }
            ))

    async def get_connection_stats(self) -> Dict:
        """获取连接统计信息"""
        stats = {
            'total': len(self.connections),
            'by_state': {},
            'by_node_type': {},
            'active': 0,
            'ready': 0
        }
        
        for connection in self.connections.values():
            # 按状态统计
            state = connection.state
            stats['by_state'][state] = stats['by_state'].get(state, 0) + 1
            
            # 按节点类型统计
            if connection.node_type:
                node_type = connection.node_type.value
                stats['by_node_type'][node_type] = stats['by_node_type'].get(node_type, 0) + 1
            
            # 活跃和就绪连接
            if connection.is_active():
                stats['active'] += 1
            if connection.is_ready():
                stats['ready'] += 1
        
        return stats
    
    async def get_connection_info(self, connection_id: str) -> Optional[Dict]:
        """获取连接详细信息"""
        if connection_id not in self.connections:
            return None
        
        connection = self.connections[connection_id]
        
        return {
            'connection_id': connection.connection_id,
            'client_addr': connection.client_addr,
            'state': connection.state,
            'last_activity': connection.last_activity,
            'worker_id': connection.worker_id,
            'node_type': connection.node_type.value if connection.node_type else None,
            'metadata': connection.metadata,
            'is_active': connection.is_active(),
            'is_ready': connection.is_ready()
        }
    
    async def get_all_connections(self) -> List[Dict]:
        """获取所有连接信息"""
        connections = []
        
        for connection_id in self.connections:
            connection_info = await self.get_connection_info(connection_id)
            if connection_info:
                connections.append(connection_info)
        
        return connections
    
    async def force_disconnect(self, connection_id: str, reason: str = "Administrative action"):
        """强制断开连接"""
        if connection_id not in self.connections:
            return False
        
        connection = self.connections[connection_id]
        
        try:
            # 发送断开连接通知
            if connection.is_ready():
                disconnect_msg = f"Disconnected: {reason}".encode('utf-8')
                response = pack_header(0x03, len(disconnect_msg)) + disconnect_msg
                await self._send_data(connection, response, packet_type=0x05)
            
            # 关闭连接
            await self.close_connection(connection_id)
            
            self.logger.info(f"强制断开连接: {connection_id}, reason: {reason}")
            return True
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            self.logger.error(f"强制断开连接错误 {connection_id}: {e}")
            return False
    
    async def cleanup_inactive_connections(self, timeout: float = 300):
        """清理不活跃的连接"""
        inactive_count = 0
        
        for connection_id, connection in list(self.connections.items()):
            if not connection.is_active(timeout):
                self.logger.info(f"清理非活动连接: {connection_id}")
                await self.close_connection(connection_id)
                inactive_count += 1
        
        self.logger.info(f"清理已完成: {inactive_count} 已删除非活动连接")
        return inactive_count

    async def get_connection_count_by_state(self) -> Dict[str, int]:
        """按状态获取连接计数"""
        count_by_state = {}
        
        for connection in self.connections.values():
            state = connection.state
            count_by_state[state] = count_by_state.get(state, 0) + 1
        
        return count_by_state
    
    async def get_connection_count_by_node_type(self) -> Dict[str, int]:
        """按节点类型获取连接计数"""
        count_by_node_type = {}
        
        for connection in self.connections.values():
            if connection.node_type:
                node_type = connection.node_type.value
                count_by_node_type[node_type] = count_by_node_type.get(node_type, 0) + 1
        
        return count_by_node_type
    
    async def get_active_connections(self) -> List[str]:
        """获取所有活跃连接的ID"""
        return [conn_id for conn_id, conn in self.connections.items() if conn.is_active()]
    
    async def get_ready_connections(self) -> List[str]:
        """获取所有就绪连接的ID"""
        return [conn_id for conn_id, conn in self.connections.items() if conn.is_ready()]
    
    async def is_connection_ready(self, connection_id: str) -> bool:
        """检查连接是否就绪"""
        if connection_id not in self.connections:
            return False
        
        return self.connections[connection_id].is_ready()
    
    async def is_connection_active(self, connection_id: str) -> bool:
        """检查连接是否活跃"""
        if connection_id not in self.connections:
            return False
        
        return self.connections[connection_id].is_active()
    
    async def get_connection_worker_id(self, connection_id: str) -> Optional[str]:
        """获取连接的Worker ID"""
        if connection_id not in self.connections:
            return None
        
        return self.connections[connection_id].worker_id
    
    async def get_connection_node_type(self, connection_id: str) -> Optional[PluginNodeType]:
        """获取连接的节点类型"""
        if connection_id not in self.connections:
            return None
        
        return self.connections[connection_id].node_type
    
    async def set_connection_node_type(self, connection_id: str, node_type: PluginNodeType):
        """设置连接的节点类型"""
        if connection_id not in self.connections:
            return False
        
        self.connections[connection_id].node_type = node_type
        self.connections[connection_id].update_activity()
        
        self.logger.debug(f"社区服务节点 {connection_id} 类型已设置: {node_type.value}")
        return True

