import asyncio
import logging
import time
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

class ConnectionState(Enum):
    INITIAL = "initial"
    HANDSHAKE = "handshake" 
    AUTHENTICATED = "authenticated"
    FORWARDING = "forwarding"
    CLOSING = "closing"
    CLOSED = "closed"


@dataclass
class ConnectionStats:
    bytes_received: int = 0
    bytes_sent: int = 0
    packets_received: int = 0
    packets_sent: int = 0
    created_at: float = time.time()
    last_activity: float = time.time()

class ConnectionManager:
    """连接管理器"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.connections: Dict[int, 'TunnelConnection'] = {}
        self.logger = logging.getLogger("ConnectionManager")
    
    def health_check(self) -> Dict:
        """连接管理器健康检查"""
        try:
            total_connections = self.count_connections()
            connection_stats = []
            
            # 收集连接统计信息
            for conn in self.connections.values():
                connection_stats.append({
                    'connection_id': conn.connection_id,
                    'state': conn.state.value if hasattr(conn.state, 'value') else str(conn.state),
                    'bytes_received': conn.stats.bytes_received,
                    'bytes_sent': conn.stats.bytes_sent,
                    'uptime': time.time() - conn.stats.created_at
                })
            
            return {
                'status': 'healthy',
                'total_connections': total_connections,
                'connection_details': connection_stats,
                'timestamp': time.time()
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'timestamp': time.time()
            }
        
    def add_connection(self, connection: 'TunnelConnection'):
        """添加新连接"""
        self.connections[connection.connection_id] = connection
        self.logger.info(f"Added connection {connection.connection_id}")
    
    def remove_connection(self, connection_id: int):
        """移除连接"""
        if connection_id in self.connections:
            del self.connections[connection_id]
            self.logger.info(f"Removed connection {connection_id}")
    
    def get_connection(self, connection_id: int) -> Optional['TunnelConnection']:
        """获取连接"""
        return self.connections.get(connection_id)
    
    def get_all_connections(self) -> List['TunnelConnection']:
        """获取所有连接"""
        return list(self.connections.values())
    
    def count_connections(self) -> int:
        """统计连接数"""
        return len(self.connections)
    
    def close_all_connections(self):
        """关闭所有连接"""
        for connection in self.connections.values():
            asyncio.create_task(connection.close())
        self.connections.clear()
        self.logger.info("Closed all connections")


class TunnelConnection:
    """隧道连接处理"""
    
    def __init__(self, connection_id: int, reader: asyncio.StreamReader,
                 writer: asyncio.StreamWriter, client_addr: tuple):
        self.connection_id = connection_id
        self.reader = reader
        self.writer = writer
        self.client_addr = client_addr
        self.state = ConnectionState.INITIAL
        self.stats = ConnectionStats()
        self.remote_connection = None  # 远程游戏服务器连接
        self.buffer_size = 8192
        self.logger = logging.getLogger(f"Connection-{connection_id}")
    
    async def handle(self):
        """处理连接生命周期"""
        try:
            self.logger.info("Handling new connection")
            
            # 握手阶段
            await self._handshake()
            
            # 认证阶段
            if not await self._authenticate():
                return
            
            # 数据转发阶段
            await self._forward_data()
            
        except asyncio.CancelledError:
            self.logger.info("Connection cancelled")
        except Exception as e:
            self.logger.error(f"Connection error: {e}")
        finally:
            await self._cleanup()
    
    async def close(self):
        """关闭连接"""
        if self.state != ConnectionState.CLOSED:
            self.state = ConnectionState.CLOSING
            await self._cleanup()
    
    async def _handshake(self):
        """握手协议"""
        self.state = ConnectionState.HANDSHAKE
        self.logger.info("Starting handshake")
        
        # 读取握手数据
        handshake_data = await self.reader.read(1024)
        if not handshake_data:
            raise ConnectionError("Client disconnected during handshake")
        
        # 解析握手信息
        handshake_info = await self._parse_handshake(handshake_data)
        
        # 建立到远程游戏服务器的连接
        self.remote_connection = await self._connect_to_game_server(handshake_info)
        
        # 发送握手响应
        await self._send_handshake_response()
        
        self.state = ConnectionState.AUTHENTICATED
        self.logger.info("Handshake completed")
    
    async def _authenticate(self) -> bool:
        """认证连接"""
        # 这里可以实现认证逻辑
        return True  # 暂时直接返回成功
    
    async def _forward_data(self):
        """数据转发（不批量处理，保持实时性）"""
        self.state = ConnectionState.FORWARDING
        self.logger.info("Starting data forwarding")
        
        # 创建双向转发任务
        client_to_server = asyncio.create_task(
            self._forward_client_to_server()
        )
        server_to_client = asyncio.create_task(
            self._forward_server_to_client()
        )
        
        # 等待任意一个任务完成（意味着连接断开）
        done, pending = await asyncio.wait(
            [client_to_server, server_to_client],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # 取消未完成的任务
        for task in pending:
            task.cancel()
        
        self.logger.info("Data forwarding ended")
    
    async def _forward_client_to_server(self):
        """从客户端转发数据到服务器"""
        try:
            while self.state == ConnectionState.FORWARDING:
                # 读取客户端数据
                data = await self.reader.read(self.buffer_size)
                if not data:
                    break  # 连接关闭
                
                # 更新统计信息
                self.stats.bytes_received += len(data)
                self.stats.packets_received += 1
                self.stats.last_activity = time.time()
                
                # 立即转发到游戏服务器
                if self.remote_connection:
                    self.remote_connection.writer.write(data)
                    await self.remote_connection.writer.drain()
                    
                    self.stats.bytes_sent += len(data)
                    self.stats.packets_sent += 1
                
        except Exception as e:
            self.logger.debug(f"Client to server error: {e}")
    
    async def _forward_server_to_client(self):
        """从服务器转发数据到客户端"""
        try:
            while self.state == ConnectionState.FORWARDING:
                # 读取服务器数据
                if not self.remote_connection:
                    break
                    
                data = await self.remote_connection.reader.read(self.buffer_size)
                if not data:
                    break  # 连接关闭
                
                # 更新统计信息
                self.stats.bytes_received += len(data)
                self.stats.packets_received += 1
                self.stats.last_activity = time.time()
                
                # 立即转发到客户端
                self.writer.write(data)
                await self.writer.drain()
                
                self.stats.bytes_sent += len(data)
                self.stats.packets_sent += 1
                
        except Exception as e:
            self.logger.debug(f"Server to client error: {e}")
    
    async def _parse_handshake(self, data: bytes) -> Dict:
        """解析握手数据"""
        # 这里实现Minecraft握手协议解析
        return {
            'server_host': '127.0.0.1',
            'server_port': 25565
        }
    
    async def _connect_to_game_server(self, handshake_info: Dict) -> 'TunnelConnection':
        """连接到远程游戏服务器"""
        try:
            reader, writer = await asyncio.open_connection(
                handshake_info['server_host'],
                handshake_info['server_port']
            )
            
            # 创建远程连接对象
            return type('RemoteConnection', (), {
                'reader': reader,
                'writer': writer
            })()
            
        except Exception as e:
            self.logger.error(f"Failed to connect to game server: {e}")
            raise
    
    async def _send_handshake_response(self):
        """发送握手响应"""
        # 实现Minecraft握手响应
        response = b"\x00"  # 示例响应
        self.writer.write(response)
        await self.writer.drain()
    
    async def _cleanup(self):
        """清理连接资源"""
        if self.state == ConnectionState.CLOSED:
            return
            
        self.state = ConnectionState.CLOSING
        self.logger.info("Cleaning up connection")
        
        # 关闭远程连接
        if self.remote_connection:
            try:
                self.remote_connection.writer.close()
                await self.remote_connection.writer.wait_closed()
            except:
                pass
        
        # 关闭客户端连接
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except:
            pass
        
        # 更新状态
        self.state = ConnectionState.CLOSED
        self.logger.info("Connection closed")
