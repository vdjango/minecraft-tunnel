import asyncio
from multiprocessing import Manager
import struct
import logging
import time
from enum import IntEnum
from typing import Dict, Any, List, Optional
from network.protocol import PacketType, ActionType, NodeType, ConnectionState, pack_byte, pack_byte_byte_byte, pack_header, pack_ulonglong, pack_ushort, pack_ushort_ushort_byte, unpack_byte_byte_byte, unpack_header, unpack_ushort
from node.executor.minecraft import ConnectionRouter, HostAffinityRegistry, TunnelDataManager, TunnelServer
from node.base import mp
import asyncio
import logging
import struct
import time
from typing import Dict, Any, Optional
from enum import IntEnum
from abc import ABC, abstractmethod

from node.mixin import NodeMixinSet
from core.plugin.types import PluginNodeType

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,  # 改为DEBUG以获取更多信息
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 设置日志
logger = logging.getLogger("PacketHandler")


class PacketHandler(ABC):
    """数据包处理基类（Master和Worker节点共用）"""
    
    def __init__(self):
        self.reader = None
        self.writer = None
        self.connected = False
    
    @abstractmethod
    async def _send_raw_data(self, data: bytes):
        """发送原始数据（由子类实现）"""
        pass
    
    @abstractmethod
    async def _receive_raw_data(self, length: int, timeout: float = 10.0) -> bytes:
        """接收原始数据（由子类实现）"""
        pass
    
    async def send_packet(self, packet_type: int, data: bytes):
        """发送数据包"""
        try:
            # 包格式: 类型(1B) | 长度(2B) | 数据(变长)
            packet_length = len(data)
            header = pack_header(packet_type, packet_length)
            packet = header + data
            await self._send_raw_data(packet)
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            logger.error(f"发送数据包错误: {e}")
            raise
    
    async def receive_packet(self, timeout: float = 10.0) -> Optional[Dict[str, Any]]:
        """接收数据包"""
        try:
            # 读取包头
            header = await asyncio.wait_for(
                self._receive_raw_data(3),
                timeout=timeout
            )
            
            packet_type, length = unpack_header(header)
            
            # 读取包体
            data = await asyncio.wait_for(
                self._receive_raw_data(length),
                timeout=timeout
            )
            
            return {
                'type': packet_type,
                'length': length,
                'data': data
            }
            
        except asyncio.TimeoutError:
            logger.warning("接收数据包超时")
            return None
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            logger.error(f"接收数据包错误: {e}")
            return None
    
    async def send_handshake(self, version: int, protocol_version: int, 
                           identifier: str, capabilities: int = 0x0F):
        """发送握手请求"""
        try:
            # 构造握手包体
            # 格式: 版本(1B) | 协议版本(1B) | ID长度(1B) | ID(变长) | 能力标志(1B)
            identifier_bytes = identifier.encode('utf-8')
            id_length = len(identifier_bytes)
            
            body_data = pack_byte_byte_byte(version, protocol_version, id_length)
            body_data += identifier_bytes
            body_data += pack_byte(capabilities)
            
            # 发送握手包
            await self.send_packet(PacketType.HANDSHAKE_REQUEST, body_data)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            logger.error(f"发送握手请求错误: {e}")
            raise
    
    async def receive_handshake_response(self, timeout: float = 10.0) -> Optional[Dict[str, Any]]:
        """接收握手响应"""
        try:
            # 接收握手响应包
            packet = await self.receive_packet(timeout)
            if not packet or packet['type'] != PacketType.HANDSHAKE_RESPONSE:
                logger.error("无效的握手响应")
                return None
            
            # 解析响应数据
            # 格式: 状态(1B) | 服务器版本(1B) | 支持的能力(1B)
            data = packet['data']
            if len(data) < 3:
                logger.error("无效的握手响应数据")
                return None
            
            status, server_version, supported_capabilities = unpack_byte_byte_byte(data[:3])
            
            if status != 0x00:  # 0x00表示成功
                logger.error(f"握手失败，状态码: {status}")
                return None
            
            logger.info(f"握手响应: 服务器版本={server_version}, 支持的能力={supported_capabilities}")
            return {
                'status': status,
                'server_version': server_version,
                'supported_capabilities': supported_capabilities
            }
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            logger.error(f"接收握手响应错误: {e}")
            return None
    
    async def close(self):
        """关闭连接"""
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
                logger.info("连接已关闭")
            except Exception as e:
                import traceback
                traceback.print_exc()
                
                logger.error(f"关闭连接错误: {e}")
            finally:
                self.reader = None
                self.writer = None
                self.connected = False


class BaseAuthenticate:
    """认证基类（确保数据包格式与服务端同步）"""
    
    def __init__(self):
        self.reader = None
        self.writer = None
        self.connected = False
    
    async def authenticate(self, credential: bytes) -> bool:
        """进行认证（与服务端同步的格式）"""
        try:
            # 发送认证请求
            await self._send_auth_request(credential)
            
            # 等待认证响应
            success = await self._receive_auth_response()
            return success
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            logger.error(f"认证错误: {e}")
            return False
    
    async def _send_auth_request(self, credential: bytes):
        """发送认证请求（与服务端同步的格式）"""
        # 认证包格式: 认证类型(1B) | 凭证长度(2B) | 凭证数据(变长)
        auth_type = 0x01  # 简单认证
        cred_length = len(credential)
        
        # 构造包体
        body_data = pack_header(auth_type, cred_length)
        body_data += credential
        
        # 发送认证包
        await self._send_packet(PacketType.AUTH_REQUEST, body_data)
    
    async def _receive_auth_response(self) -> bool:
        """接收认证响应（与服务端同步的格式）"""
        # 接收认证响应包
        response = await self._receive_packet_response(PacketType.AUTH_RESPONSE)
        if response['status'] != 0x00:  # 0x00表示成功
            logger.error(f"认证失败，状态码: {response['status']}, 消息: {response['message']}")
            return False
        
        return True
    
    async def _send_packet(self, packet_type: int, data: bytes):
        """发送数据包（通用方法）"""
        # 包格式: 类型(1B) | 长度(2B) | 数据(变长)
        packet_length = len(data)
        header = pack_header(packet_type, packet_length)
        packet = header + data
        
        # 检查写入器是否有效
        if not self.writer or self.writer.is_closing():
            logger.error("写入器不可用或正在关闭")
            raise ConnectionError("写入器不可用")
        
        # 发送数据
        self.writer.write(packet)
        await self.writer.drain()
    
    async def _receive_packet_response(self, expected_packet_type: int, timeout: int = 10) -> Dict[str, Any]:
        """接收包响应（通用方法，与服务端同步）"""
        try:
            # 读取响应包头
            header = await asyncio.wait_for(
                self.reader.readexactly(3),
                timeout=timeout
            )
            packet_type, length = unpack_header(header)
            if packet_type != expected_packet_type:
                raise ValueError(f"意外的包类型: {packet_type}, 期望 {expected_packet_type}")
            
            # 读取响应包体
            data = await asyncio.wait_for(
                self.reader.readexactly(length),
                timeout=timeout
            )
            
            # 解析响应（与服务端同步的格式）
            # 响应格式: 状态(1B) | 消息长度(2B) | 消息(变长) | 额外数据(变长)
            if len(data) < 3:
                return {
                    'status': 0x01,  # 默认错误状态
                    'message': '无效的响应格式',
                    'data': b''
                }
            
            status = data[0]
            msg_length = unpack_ushort(data[1:3])  # [0]
            
            # 提取消息
            message = ""
            if msg_length > 0:
                if len(data) < 3 + msg_length:
                    return {
                        'status': 0x01,
                        'message': '无效的消息长度',
                        'data': b''
                    }
                message = data[3:3+msg_length].decode('utf-8')
            
            # 提取额外数据
            extra_data = data[3+msg_length:] if len(data) > 3 + msg_length else b""
            
            return {
                'status': status,
                'message': message,
                'data': extra_data
            }
            
        except asyncio.TimeoutError:
            logger.error("等待包响应超时")
            return {
                'status': 0x02,  # 超时状态
                'message': '超时',
                'data': b''
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            logger.error(f"接收包响应错误: {e}")
            return {
                'status': 0x03,  # 错误状态
                'message': str(e),
                'data': b''
            }


class ClientHandler(PacketHandler, BaseAuthenticate):
    """客户端 提供基础连接 认证 注册 节点获取"""
    
    def __init__(self, master_host: str, master_port: int, worker_id: str):
        super().__init__()
        self.master_host = master_host
        self.master_port = master_port
        self.worker_id = worker_id
        self.session_id = None

        self.connection = None
        self.connected = False
        self.keepalive_interval = 30  # 心跳间隔（秒）
        self.keepalive_task = None
    
    async def _send_raw_data(self, data: bytes):
        """发送原始数据"""
        if not self.writer or self.writer.is_closing():
            raise ConnectionError("写入器不可用")
        
        self.writer.write(data)
        await self.writer.drain()
    
    async def _receive_raw_data(self, length: int, timeout: float = 10.0) -> bytes:
        """接收原始数据"""
        if not self.reader:
            raise ConnectionError("读取器不可用")
        
        return await asyncio.wait_for(
            self.reader.readexactly(length),
            timeout=timeout
        )
    
    async def connect(self):
        """连接到Master服务器"""
        try:
            # 建立TCP连接
            self.reader, self.writer = await asyncio.open_connection(
                self.master_host, self.master_port
            )
            
            logger.info(f"已连接到 {self.master_host}:{self.master_port}")
            
            # 发送握手请求
            await self.send_handshake(
                version=1,
                protocol_version=1,
                identifier=self.worker_id,
                capabilities=0x0F
            )
            
            # 接收握手响应
            response = await self.receive_handshake_response()
            if not response:
                logger.error("握手失败")
                await self.close()
                return False
            
            self.connected = True
            return True
        
        except ConnectionRefusedError as e:
            await self.close()
            raise ConnectionRefusedError(f"主机服务不在线，无法建立远程连接 {self.master_host}:{self.master_port}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            logger.error(f"连接错误: {e}")
            await self.close()
            return False
    
    async def loop(self):
        # 启动心跳任务
        self.keepalive_task = asyncio.create_task(self.keepalive_loop())

    async def keepalive_loop(self):
        """心跳循环"""
        while self.connected:
            try:
                await self.send_heartbeat()
                await asyncio.sleep(self.keepalive_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"心跳错误: {e}")

    async def shutdown(self, timeout = 10):
        # 停止心跳任务
        if self.keepalive_task:
            self.keepalive_task.cancel()
            try:
                await self.keepalive_task
            except asyncio.CancelledError:
                pass
        
        return await super().shutdown(timeout)

    async def request_node(self, client_type: int, game_version: str, mods_info: str = "") -> Dict[str, Any]:
        """请求分配节点（优化版）"""
        try:
            # 构造请求数据
            game_version_bytes = game_version.encode('utf-8')
            mods_info_bytes = mods_info.encode('utf-8') if mods_info else b""
            
            body_data = pack_byte(client_type)
            body_data += pack_byte(len(game_version_bytes))
            body_data += game_version_bytes
            body_data += pack_ushort(len(mods_info_bytes))
            body_data += mods_info_bytes
            
            # 发送请求
            await self.send_packet(PacketType.REQUEST_NODE, body_data)
            
            # 接收响应（带超时）
            try:
                response = await asyncio.wait_for(
                    self.receive_packet(PacketType.REQUEST_NODE),
                    timeout=10.0  # 10秒超时
                )
            except asyncio.TimeoutError:
                return {"success": False, "error": "请求超时"}
            
            if not response:
                return {"success": False, "error": "未收到响应"}
            
            # 解析响应数据
            data = response['data']
            if len(data) < 1:
                return {"success": False, "error": "无效的响应格式"}
            
            # 检查状态码
            status = data[0]
            if status == 0x00:  # 成功响应
                # 成功响应格式: 状态(1B) | 节点ID长度(1B) | 节点ID(变长) | 主机长度(1B) | 主机(变长) | 端口(2B)
                if len(data) < 2:
                    return {"success": False, "error": "无效的成功响应格式"}
                
                node_id_len = data[1]
                if len(data) < 2 + node_id_len + 1:
                    return {"success": False, "error": "节点ID数据不完整"}
                
                node_id = data[2:2+node_id_len].decode('utf-8')
                host_len = data[2+node_id_len]
                
                if len(data) < 2 + node_id_len + 1 + host_len + 2:
                    return {"success": False, "error": "主机或端口数据不完整"}
                
                host = data[3+node_id_len:3+node_id_len+host_len].decode('utf-8')
                port = unpack_ushort(data[3+node_id_len+host_len:5+node_id_len+host_len])
                
                return {
                    'success': True,
                    'node_id': node_id,
                    'host': host,
                    'port': port
                }
            else:  # 错误响应
                # 错误响应格式: 状态(1B) | 消息长度(2B) | 消息(变长)
                if len(data) < 3:
                    return {"success": False, "error": "无效的错误响应格式"}
                
                msg_length = unpack_ushort(data[1:3])
                
                if len(data) < 3 + msg_length:
                    return {"success": False, "error": "错误消息不完整"}
                
                error_msg = data[3:3+msg_length].decode('utf-8')
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            logger.error(f"请求节点错误: {e}")
            return {"success": False, "error": f"请求失败: {str(e)}"}
    
    async def register_node(self, node_id: Any, node_type: int, host: str, port: int, 
                          capacity: int = 100, capabilities: int = 0x0F) -> bool:
        """注册节点"""
        try:
            # 构造注册数据
            host_bytes = host.encode('utf-8')
            
            body_data = pack_byte(node_type)
            body_data += pack_byte(len(host_bytes))
            body_data += host_bytes
            body_data += pack_ushort_ushort_byte(port, capacity, capabilities)
            
            # 发送注册请求
            await self.send_packet(PacketType.REGISTER_NODE, body_data)
            
            # 接收响应
            response = await self.receive_packet()
            if not response or response['type'] != PacketType.REGISTER_NODE:
                return False
            
            # 解析响应
            data = response['data']
            if len(data) < 1:
                return False
            
            status = data[0]
            return status == 0x00  # 0x00表示成功
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            logger.error(f"注册节点错误: {e}")
            return False
    
    async def send_heartbeat(self) -> bool:
        """发送心跳包"""
        try:
            # 构造心跳数据
            timestamp = int(time.time() * 1000)
            heartbeat_data = pack_ulonglong(timestamp)
            await self.send_packet(PacketType.HEARTBEAT, heartbeat_data)
            
            # 接收响应
            response = await self.receive_packet()
            if not response or response['type'] != PacketType.HEARTBEAT:
                return False
            
            data = response['data']
            if len(data) < 1:
                return False
            
            status = data[0]
            return status == 0x00  # 0x00表示成功
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            logger.error(f"发送心跳包错误: {e}")
            return False
    
    async def disconnect(self, reason: str = "客户端请求") -> bool:
        """断开连接"""
        # 停止心跳任务
        if self.keepalive_task:
            self.keepalive_task.cancel()
            try:
                await self.keepalive_task
            except asyncio.CancelledError:
                pass

        try:
            # 构造断开连接数据
            reason_bytes = reason.encode('utf-8')
            disconnect_data = pack_ushort(len(reason_bytes))
            disconnect_data += reason_bytes
            
            # 发送断开连接请求
            await self.send_packet(PacketType.DISCONNECT, disconnect_data)
            
            # 接收响应（可选）
            try:
                response = await asyncio.wait_for(
                    self.receive_packet(),
                    timeout=2.0
                )
                if response and response['type'] == PacketType.DISCONNECT:
                    data = response['data']
                    if len(data) > 0:
                        status = data[0]
                        return status == 0x00
            except (asyncio.TimeoutError, Exception):
                # 超时或其他错误不影响断开连接
                pass
            
            return True
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            logger.error(f"断开连接错误: {e}")
            return False
        finally:
            # 无论如何都关闭连接
            await self.close()


class WorkerServer(NodeMixinSet):
    """主节点服务，负责协调节点分发和管理工作节点
    1. 注册社区服务节点（部署的节点服务器需要加入网络）
    2. 请求分配节点（玩家联机时请求分配的节点主机）"""
    node_executor = TunnelServer
    
    def __init__(self, config: Dict):
        super(WorkerServer, self).__init__(config)
        self.router_port = 3000
        self.control_port = 5050
        self.forward_port = 6060
        self.node_type = PluginNodeType.WORKER
        self.connections_sharing_manager = TunnelDataManager()
        self.logger = logging.getLogger(f"[MAIN] NodeX {self.__class__.__name__}")
        self.client = ClientHandler(
            master_host="localhost",
            master_port="3332",
            worker_id="main"
        )
        # 创建多进程管理器
        manager = Manager()

        # 创建主机亲和性注册表
        self.host_affinity = HostAffinityRegistry(manager)
        # 创建连接路由器
        self.router = ConnectionRouter(self.host_affinity, {})
    
    async def set_node_id(self):
        self.node_id = 'Worker节点唯一ID'

    async def run_until(self, worker_id, *args, **kwargs):
        worker = self.node_executor(worker_id, *args, **kwargs)
        await worker.start()

    async def start_worker(self, worker_processes: str = 'auto'):
        """启动节点"""
        worker_count = mp.cpu_count()
        if worker_processes != 'auto':
            worker_count = int(worker_processes)
        
        workers = []
        for worker_id in range(worker_count):
            # 注册进程路由
            await self.router.register_worker(
                worker_id,
                control_port=self.control_port + worker_id,
                forward_port=self.forward_port + worker_id
            )
            # 启动工作进程
            workers.append(await self.create_worker(
                worker_id,
                control_port=self.control_port + worker_id,
                forward_port=self.forward_port + worker_id
            ))

        # 启动路由服务
        asyncio.create_task(self.router.start_router('0.0.0.0', self.router_port))
        return workers
    
    async def connect_master(self):
        """与Master节点建立连接并完成注册"""
        try:
            if await self.client.connect():
                # 进行认证
                auth_success = await self.client.authenticate(b"secure_auth_key")
                if not auth_success:
                    logger.error(f"Authentication failed")

                # 注册为社区服务节点
                result = await self.client.register_node(
                    node_id=1,
                    node_type=PluginNodeType.WORKER,
                    host="192.168.1.100",
                    port=8080,
                    capacity=100,
                    capabilities=0x0F
                )
                if not result:
                    print("注册节点服务失败", result)
                
                # result = await client.register_node(
                #     node_id=2,
                #     node_type=PluginNodeType.WORKER,
                #     host="192.168.1.100",
                #     port=8080,
                #     capacity=100,
                #     capabilities=0x0F
                # )
                # if not result:
                #     print("注册节点服务失败", result)
                
                # result = await client.register_node(
                #     node_id=3,
                #     node_type=PluginNodeType.WORKER,
                #     host="192.168.1.100",
                #     port=8080,
                #     capacity=100,
                #     capabilities=0x0F
                # )
                # if not result:
                #     print("注册节点服务失败", result)

                return self.client
        except ConnectionRefusedError as e:
            self.logger.warning(e)
            
        return None
    
    async def start(self):
        """启动主节点"""
        # 启动Worker节点并向Master注册，维持心跳 TODO 心跳是否维持、是否保持长连接
        if await self.connect_master():
            await asyncio.sleep(1)
            print('请求分配节点')
            # 请求分配节点 TODO 此为测试
            result = await self.client.request_node(
                client_type=NodeType.PLAYER_CLIENT,
                game_version="1.18.2",
                mods_info="forge-39.0.0"
            )
            if result['success']:
                print(f"请求分配节点: {result['node_id']} at {result['host']}:{result['port']}")
            else:
                print(f"请求分配节点失败: {result['error']}")

            asyncio.create_task(self.client.loop())

        self.workers = await self.start_worker(worker_processes=8)
