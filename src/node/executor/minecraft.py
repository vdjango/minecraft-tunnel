# tunnel_server_async.py
import json
from multiprocessing import Manager
import uuid
import random
import asyncio
import logging
import time
import signal
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Any

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("tunnel_server_async.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("TunnelServerAsync")

def signal_handler(sig, frame):
    logger.info("检测到Ctrl+C，程序正在退出...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)


class IDGenerator:
    """自增计数器（无需修改）"""
    def __init__(self):
        self._lock = asyncio.Lock()
        self._next_id = 1
        self.items = [i for i in 'qwertyuiopasdfghjklzxcvbnm,./;-=!@#$%^&*()_+<>?:']
    
    def randint(self):
        return str(random.randint(10000, 90000))
    
    def sample(self):
        return ''.join(random.sample(self.items, 5))

    def uidx(self, name):
        return uuid.uuid5(uuid.NAMESPACE_DNS, str(name))

    async def get_next_id(self, name):
        async with self._lock:
            id = self._next_id
            self._next_id += 1
            return self.uidx(str(name) + str(id) + self.randint() + self.sample()).hex


class SessionManager:
    """会话管理器（无需修改）"""
    def __init__(self):
        self.sessions = {}  # session_id -> {host_conn, client_conn, host_id, client_id}
        self.host_sessions = defaultdict(list)  # host_id -> [session_ids]
        self.lock = asyncio.Lock()
        self.next_session_id = 1
    
    async def create_session(self, host_id, host_conn, client_id, client_conn):
        async with self.lock:
            session_id = self.next_session_id
            self.next_session_id += 1
            
            self.sessions[session_id] = {
                'host_conn': host_conn,
                'client_conn': client_conn,
                'host_id': host_id,
                'client_id': client_id,
                'created_at': time.time()
            }
            
            self.host_sessions[host_id].append(session_id)
            return session_id
    
    async def remove_session(self, session_id):
        async with self.lock:
            if session_id in self.sessions:
                session = self.sessions[session_id]
                host_id = session['host_id']
                
                # 从主机会话列表中移除
                if host_id in self.host_sessions and session_id in self.host_sessions[host_id]:
                    self.host_sessions[host_id].remove(session_id)
                
                # 清理空的主机条目
                if host_id in self.host_sessions and not self.host_sessions[host_id]:
                    del self.host_sessions[host_id]
                
                del self.sessions[session_id]
    
    async def get_session(self, session_id):
        async with self.lock:
            return self.sessions.get(session_id)
    
    async def get_host_sessions(self, host_id):
        async with self.lock:
            return [self.sessions[sid] for sid in self.host_sessions.get(host_id, [])]


class HostAffinityRegistryx:
    """主机亲和性注册表（多进程共享）"""
    
    def __init__(self, manager: Manager):
        self.manager = manager
        self.host_to_worker = self.manager.dict()  # host_id -> worker_id
        self.worker_to_hosts = self.manager.dict()  # worker_id -> set(host_ids)
        self.lock = self.manager.Lock()
    
    def register_host(self, host_id: str, worker_id: str):
        """注册主机到工作进程"""
        with self.lock:
            self.host_to_worker[host_id] = worker_id
            if worker_id not in self.worker_to_hosts:
                self.worker_to_hosts[worker_id] = self.manager.list()
            if host_id not in self.worker_to_hosts[worker_id]:
                self.worker_to_hosts[worker_id].append(host_id)
    
    def unregister_host(self, host_id: str):
        """注销主机"""
        with self.lock:
            if host_id in self.host_to_worker:
                worker_id = self.host_to_worker[host_id]
                del self.host_to_worker[host_id]
                if worker_id in self.worker_to_hosts and host_id in self.worker_to_hosts[worker_id]:
                    self.worker_to_hosts[worker_id].remove(host_id)
    
    def get_worker_for_host(self, host_id: str) -> Optional[str]:
        """获取主机所在的工作进程"""
        with self.lock:
            return self.host_to_worker.get(host_id)
    
    def get_hosts_for_worker(self, worker_id: str) -> List[str]:
        """获取工作进程上的所有主机"""
        with self.lock:
            return list(self.worker_to_hosts.get(worker_id, []))


class ConnectionRouterx:
    """连接路由器（多进程路由）"""
    
    def __init__(self, host_affinity: HostAffinityRegistryx, worker_ports: Dict[str, tuple]):
        """
        初始化连接路由器
        
        Args:
            host_affinity: 主机亲和性注册表
            worker_ports: 工作进程端口映射 {worker_id: (control_port, forward_port)}
        """
        self.host_affinity = host_affinity
        self.worker_ports = worker_ports
        self.router_server = None
        self.running = True
    
    async def start_router(self, host='0.0.0.0', port=3000):
        """启动路由服务器"""
        try:
            self.router_server = await asyncio.start_server(
                self.handle_router_connection,
                host, port,
                reuse_address=True,
                reuse_port=True,
                backlog=100
            )
            
            logger.info(f"路由服务器启动在 {host}:{port}")
            
            # 存储服务器地址信息，供客户端查询
            self.router_host = host
            self.router_port = port
            
            async with self.router_server:
                await self.router_server.serve_forever()
                
        except Exception as e:
            logger.error(f"启动路由服务器失败: {e}")
            raise
    
    async def handle_router_connection(self, reader, writer):
        """处理路由连接请求"""
        addr = writer.get_extra_info('peername')
        logger.info(f"收到路由请求来自: {addr}")
        
        try:
            # 读取客户端请求
            data = await reader.read(1024)
            if not data:
                return
            
            request = json.loads(data.decode())
            host_id = request.get('host_id')
            client_id = request.get('client_id')
            action = request.get('action', 'route')
            
            if not host_id:
                # 返回错误响应
                response = {'status': 'error', 'error': 'Missing host_id'}
                writer.write(json.dumps(response).encode())
                await writer.drain()
                return
            
            if action == 'register':
                # 注册新主机
                worker_id = request.get('worker_id')
                if not worker_id:
                    response = {'status': 'error', 'error': 'Missing worker_id for registration'}
                    writer.write(json.dumps(response).encode())
                    await writer.drain()
                    return
                
                # 注册主机到工作进程
                self.host_affinity.register_host(host_id, worker_id)
                response = {'status': 'success', 'message': f'Host {host_id} registered to worker {worker_id}'}
                writer.write(json.dumps(response).encode())
                await writer.drain()
                logger.info(f"注册主机 {host_id} 到工作进程 {worker_id}")
                
            elif action == 'unregister':
                # 注销主机
                self.host_affinity.unregister_host(host_id)
                response = {'status': 'success', 'message': f'Host {host_id} unregistered'}
                writer.write(json.dumps(response).encode())
                await writer.drain()
                logger.info(f"注销主机 {host_id}")
                
            elif action == 'route':
                # 路由请求 - 查找主机所在的工作进程
                worker_id = self.host_affinity.get_worker_for_host(host_id)
                if not worker_id:
                    # 返回错误响应
                    response = {'status': 'error', 'error': f'Host {host_id} not found'}
                    writer.write(json.dumps(response).encode())
                    await writer.drain()
                    logger.warning(f"未找到主机 {host_id} 的路由信息")
                    return
                
                # 获取工作进程的端口信息
                if worker_id not in self.worker_ports:
                    response = {'status': 'error', 'error': f'Worker {worker_id} not available'}
                    writer.write(json.dumps(response).encode())
                    await writer.drain()
                    logger.error(f"工作进程 {worker_id} 不可用")
                    return
                
                control_port, forward_port = self.worker_ports[worker_id]
                
                # 返回路由信息
                response = {
                    'status': 'success',
                    'host_id': host_id,
                    'worker_id': worker_id,
                    'control_port': control_port,
                    'forward_port': forward_port,
                    'host': '81.68.225.236'  # 实际部署时可以是具体IP
                }
                
                writer.write(json.dumps(response).encode())
                await writer.drain()
                logger.info(f"路由请求: 主机 {host_id} -> 工作进程 {worker_id}")
                
            else:
                response = {'status': 'error', 'error': f'Unknown action: {action}'}
                writer.write(json.dumps(response).encode())
                await writer.drain()
                
        except json.JSONDecodeError:
            response = {'status': 'error', 'error': 'Invalid JSON format'}
            writer.write(json.dumps(response).encode())
            await writer.drain()
            logger.error(f"无效的JSON格式来自 {addr}")
            
        except Exception as e:
            logger.error(f"处理路由请求错误: {e}")
            response = {'status': 'error', 'error': f'Internal server error: {str(e)}'}
            writer.write(json.dumps(response).encode())
            await writer.drain()
            
        finally:
            writer.close()
            await writer.wait_closed()
    
    async def get_route_info(self, host_id):
        """获取主机的路由信息（供其他组件调用）"""
        worker_id = self.host_affinity.get_worker_for_host(host_id)
        if not worker_id or worker_id not in self.worker_ports:
            return None
        
        control_port, forward_port = self.worker_ports[worker_id]
        return {
            'host_id': host_id,
            'worker_id': worker_id,
            'control_port': control_port,
            'forward_port': forward_port
        }
    
    async def register_worker(self, worker_id, control_port, forward_port):
        """注册工作进程"""
        self.worker_ports[worker_id] = (control_port, forward_port)
        logger.info(f"注册工作进程 {worker_id}: 控制端口={control_port}, 转发端口={forward_port}")
    
    async def unregister_worker(self, worker_id):
        """注销工作进程"""
        if worker_id in self.worker_ports:
            del self.worker_ports[worker_id]
            logger.info(f"注销工作进程 {worker_id}")
    
    async def shutdown(self):
        """关闭路由服务器"""
        self.running = False
        if self.router_server:
            self.router_server.close()
            await self.router_server.wait_closed()
            logger.info("路由服务器已关闭")

class HostAffinityRegistry:
    """主机亲和性注册表（多进程共享）"""
    
    def __init__(self, manager: Manager):
        self.manager = manager
        self.host_to_worker = self.manager.dict()  # host_id -> worker_id
        self.worker_to_hosts = self.manager.dict()  # worker_id -> set(host_ids)
        self.worker_load = self.manager.dict()      # worker_id -> connection_count
        self.lock = self.manager.Lock()
    
    def register_host(self, host_id: str, worker_id: str):
        """注册主机到工作进程"""
        with self.lock:
            self.host_to_worker[host_id] = worker_id
            if worker_id not in self.worker_to_hosts:
                self.worker_to_hosts[worker_id] = self.manager.list()
            if host_id not in self.worker_to_hosts[worker_id]:
                self.worker_to_hosts[worker_id].append(host_id)
    
    def unregister_host(self, host_id: str):
        """注销主机"""
        with self.lock:
            if host_id in self.host_to_worker:
                worker_id = self.host_to_worker[host_id]
                del self.host_to_worker[host_id]
                if worker_id in self.worker_to_hosts and host_id in self.worker_to_hosts[worker_id]:
                    self.worker_to_hosts[worker_id].remove(host_id)
    
    def get_worker_for_host(self, host_id: str) -> Optional[str]:
        """获取主机所在的工作进程"""
        with self.lock:
            return self.host_to_worker.get(host_id)
    
    def get_hosts_for_worker(self, worker_id: str) -> List[str]:
        """获取工作进程上的所有主机"""
        with self.lock:
            return list(self.worker_to_hosts.get(worker_id, []))
    
    def update_worker_load(self, worker_id: str, delta: int = 1):
        """更新工作进程负载"""
        with self.lock:
            current_load = self.worker_load.get(worker_id, 0)
            self.worker_load[worker_id] = current_load + delta
    
    def get_worker_load(self, worker_id: str) -> int:
        """获取工作进程负载"""
        with self.lock:
            return self.worker_load.get(worker_id, 0)
    
    def get_least_loaded_worker(self) -> Optional[str]:
        """获取负载最轻的工作进程"""
        with self.lock:
            if not self.worker_load:
                return None
            
            # 找到负载最轻的工作进程
            min_load = float('inf')
            least_loaded = None
            
            for worker_id, load in self.worker_load.items():
                if load < min_load:
                    min_load = load
                    least_loaded = worker_id

            if not least_loaded:
                least_loaded = self.worker_load.keys()[0]
            
            return least_loaded


class ConnectionRouter:
    """连接路由器（多进程路由，支持负载均衡）"""
    
    def __init__(self, host_affinity: HostAffinityRegistry, worker_ports: Dict[str, tuple]):
        """
        初始化连接路由器
        
        Args:
            host_affinity: 主机亲和性注册表
            worker_ports: 工作进程端口映射 {worker_id: (control_port, forward_port)}
        """
        self.host_affinity = host_affinity
        self.worker_ports = worker_ports
        self.router_server = None
        self.running = True
    
    async def start_router(self, host='0.0.0.0', port=3000):
        """启动路由服务器"""
        try:
            self.router_server = await asyncio.start_server(
                self.handle_router_connection,
                host, port,
                reuse_address=True,
                reuse_port=True,
                backlog=100
            )
            
            logger.info(f"路由服务器启动在 {host}:{port}")
            
            # 存储服务器地址信息，供客户端查询
            self.router_host = host
            self.router_port = port
            
            async with self.router_server:
                await self.router_server.serve_forever()
                
        except Exception as e:
            logger.error(f"启动路由服务器失败: {e}")
            raise
    
    async def handle_router_connection(self, reader, writer):
        """处理路由连接请求"""
        addr = writer.get_extra_info('peername')
        logger.info(f"收到路由请求来自: {addr}")
        
        try:
            # 读取客户端请求
            data = await reader.read(1024)
            if not data:
                return
            
            request = json.loads(data.decode())
            host_id = request.get('host_id')
            client_id = request.get('client_id')
            action = request.get('action', 'route')
            
            if not host_id:
                # 返回错误响应
                response = {'status': 'error', 'error': 'Missing host_id'}
                writer.write(json.dumps(response).encode())
                await writer.drain()
                return
            
            if action == 'register':
                # 注册新主机 - 自动选择负载最轻的工作进程
                worker_id = self.host_affinity.get_least_loaded_worker()
                print('worker_id', worker_id)
                if not worker_id and worker_id != 0:
                    response = {'status': 'error', 'error': 'No available workers'}
                    writer.write(json.dumps(response).encode())
                    await writer.drain()
                    return
                
                # 注册主机到工作进程
                self.host_affinity.register_host(host_id, worker_id)
                response = {
                    'status': 'success',
                    'message': f'Host {host_id} registered to worker {worker_id}',
                    'worker_id': worker_id,
                    'host': '81.68.225.236',  # 实际部署时可以是具体IP
                    'control_port': self.worker_ports[worker_id][0],
                    'forward_port': self.worker_ports[worker_id][1]
                }
                writer.write(json.dumps(response).encode())
                await writer.drain()
                logger.info(f"注册主机 {host_id} 到工作进程 {worker_id}")
                
            elif action == 'unregister':
                # 注销主机
                self.host_affinity.unregister_host(host_id)
                response = {'status': 'success', 'message': f'Host {host_id} unregistered'}
                writer.write(json.dumps(response).encode())
                await writer.drain()
                logger.info(f"注销主机 {host_id}")
                
            elif action == 'route':
                # 路由请求 - 查找主机所在的工作进程
                worker_id = self.host_affinity.get_worker_for_host(host_id)
                print(worker_id)
                if not worker_id and worker_id != 0:
                    # 返回错误响应
                    response = {'status': 'error', 'error': f'Host {host_id} not found'}
                    writer.write(json.dumps(response).encode())
                    await writer.drain()
                    logger.warning(f"未找到主机 {host_id} 的路由信息")
                    return
                
                # 获取工作进程的端口信息
                if worker_id not in self.worker_ports:
                    response = {'status': 'error', 'error': f'Worker {worker_id} not available'}
                    writer.write(json.dumps(response).encode())
                    await writer.drain()
                    logger.error(f"工作进程 {worker_id} 不可用")
                    return
                
                # 更新工作进程负载
                self.host_affinity.update_worker_load(worker_id)
                
                control_port, forward_port = self.worker_ports[worker_id]
                
                # 返回路由信息
                response = {
                    'status': 'success',
                    'host_id': host_id,
                    'worker_id': worker_id,
                    'control_port': control_port,
                    'forward_port': forward_port,
                    'host': '81.68.225.236',  # 实际部署时可以是具体IP
                    'load': self.host_affinity.get_worker_load(worker_id)
                }
                
                writer.write(json.dumps(response).encode())
                await writer.drain()
                logger.info(f"路由请求: 主机 {host_id} -> 工作进程 {worker_id}, 负载: {response['load']}")
                
            elif action == 'stats':
                # 获取统计信息
                stats = {}
                for worker_id in self.worker_ports.keys():
                    stats[worker_id] = {
                        'host_count': len(self.host_affinity.get_hosts_for_worker(worker_id)),
                        'load': self.host_affinity.get_worker_load(worker_id),
                        'ports': self.worker_ports[worker_id]
                    }
                
                response = {'status': 'success', 'stats': stats}
                writer.write(json.dumps(response).encode())
                await writer.drain()
                
            else:
                response = {'status': 'error', 'error': f'Unknown action: {action}'}
                writer.write(json.dumps(response).encode())
                await writer.drain()
                
        except json.JSONDecodeError:
            response = {'status': 'error', 'error': 'Invalid JSON format'}
            writer.write(json.dumps(response).encode())
            await writer.drain()
            logger.error(f"无效的JSON格式来自 {addr}")
            
        except Exception as e:
            logger.error(f"处理路由请求错误: {e}")
            response = {'status': 'error', 'error': f'Internal server error: {str(e)}'}
            writer.write(json.dumps(response).encode())
            await writer.drain()
            
        finally:
            writer.close()
            await writer.wait_closed()
    
    async def get_route_info(self, host_id):
        """获取主机的路由信息（供其他组件调用）"""
        worker_id = self.host_affinity.get_worker_for_host(host_id)
        if not worker_id or worker_id not in self.worker_ports:
            return None
        
        control_port, forward_port = self.worker_ports[worker_id]
        return {
            'host_id': host_id,
            'worker_id': worker_id,
            'control_port': control_port,
            'forward_port': forward_port,
            'load': self.host_affinity.get_worker_load(worker_id)
        }
    
    async def register_worker(self, worker_id, control_port, forward_port):
        """注册工作进程"""
        self.worker_ports[worker_id] = (control_port, forward_port)
        # 初始化负载为0
        self.host_affinity.update_worker_load(worker_id, 0)
        logger.info(f"注册工作进程 {worker_id}: 控制端口={control_port}, 转发端口={forward_port}")
    
    async def unregister_worker(self, worker_id):
        """注销工作进程"""
        if worker_id in self.worker_ports:
            # 移除该工作进程的所有主机
            host_ids = self.host_affinity.get_hosts_for_worker(worker_id)
            for host_id in host_ids:
                self.host_affinity.unregister_host(host_id)
            
            # 移除工作进程
            del self.worker_ports[worker_id]
            logger.info(f"注销工作进程 {worker_id}")
    
    async def update_load(self, worker_id, delta=1):
        """更新工作进程负载"""
        self.host_affinity.update_worker_load(worker_id, delta)
    
    async def shutdown(self):
        """关闭路由服务器"""
        self.running = False
        if self.router_server:
            self.router_server.close()
            await self.router_server.wait_closed()
            logger.info("路由服务器已关闭")


class TunnelDataManager:
    """多进程数据共享"""
    def __init__(self, manager: Optional[Manager] = None):
        # 使用多进程管理器创建共享数据结构
        self.manager = manager or Manager()

        # 连接管理
        self.control_connections = self.manager.dict()  # id -> (reader, writer)
        self.forward_connections = self.manager.dict()  # id -> (reader, writer)
    

class TunnelServer:
    """异步版本的隧道服务器"""

    def __init__(self, worker_id: str, host='0.0.0.0', control_port=3333, forward_port=3334, connections_manager: TunnelDataManager = None):
        self._shutdown_task = None  # 用于跟踪关闭任务

        self.worker_id = worker_id
        # self.node_id = node_id
        self.host = host
        self.control_port = control_port  # 控制连接端口
        self.forward_port = forward_port  # 数据连接端口
        self.running = True
        
        # 会话管理
        self.session_manager = SessionManager()
        # ID自增器
        self.idgx = IDGenerator()
        #
        # self.connections_manager: TunnelDataManager = connections_manager
        
        # 使用多进程管理器创建共享数据结构
        # self.manager = manager or Manager()

        # 连接管理
        self.control_connections = {}  # self.manager.dict()  # id -> (reader, writer)
        self.forward_connections = {}  # self.manager.dict()  # id -> (reader, writer)
        self.conn_lock = asyncio.Lock()
        
        # 服务套接字
        self.control_server = None
        self.forward_server = None

    def _setup_signal_handlers(self):
        """设置信号处理器"""
        # 获取主事件循环
        loop = asyncio.get_running_loop()
        # 注册信号处理
        for sig in [signal.SIGTERM, signal.SIGINT]:
            loop.add_signal_handler(sig, lambda s=sig: self._signal_handler(s))

    def _signal_handler(self, signum):
        """信号处理"""
        logger.debug(f"[{self.worker_id}] 收到信号 {signum}，正在关闭...")
        
        # 如果已经有关闭任务在运行，则不再创建新任务
        if self._shutdown_task is None:
            self._shutdown_task = asyncio.create_task(self.shutdown())

    # @property
    # def control_connections(self):
    #     return self.connections_manager.control_connections
    
    # @property
    # def forward_connections(self):
    #     return self.connections_manager.forward_connections
    
    async def forward_data(self, src_reader, src_writer, dst_writer, description, session_id):
        """通用数据转发函数（异步版本）"""
        try:
            while True:
                try:
                    data = await src_reader.read(4096)
                    if not data:
                        logger.info(f"[{self.worker_id}] 会话{session_id}: {description} 连接关闭")
                        break
                    dst_writer.write(data)
                    await dst_writer.drain()
                except ConnectionResetError:
                    logger.info(f"[{self.worker_id}] 会话{session_id}: {description} 连接被重置")
                    break
                except ConnectionAbortedError:
                    logger.info(f"[{self.worker_id}] 会话{session_id}: {description} 连接被中止")
                    break
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"[{self.worker_id}] 会话{session_id}: {description} 数据转发错误: {e}")
                    break
                
        except Exception as e:
            logger.error(f"[{self.worker_id}] 会话{session_id}: {description} 转发任务异常: {e}")
        finally:
            # 清理会话
            await self.session_manager.remove_session(session_id)
            try:
                src_writer.close()
                await src_writer.wait_closed()
            except:
                pass
            try:
                dst_writer.close()
                await dst_writer.wait_closed()
            except:
                pass

    async def heartbeat(self, type_id, typec='host'):
        """心跳（异步版本）"""
        if type_id not in self.control_connections:
            return
            
        reader, writer = self.control_connections[type_id]

        try:
            while self.running:
                # 发送心跳保持连接
                try:
                    writer.write(json.dumps({'type': 'heartbeat', 'id': type_id}).encode('utf-8'))
                    await writer.drain()
                    await asyncio.sleep(5)
                except:
                    logger.info(f"[{self.worker_id}] [控制] {'主机' if typec == 'host' else '客户端'} {type_id} 连接断开, 当前数据端活跃 {len(self.forward_connections.keys())}")
                    break

                logger.info(f"[{self.worker_id}] [控制] 当前转发客户端(主机不会关闭，是长连接) {'主机' if typec == 'host' else '客户端'} {len(self.control_connections.keys())} {len(self.forward_connections.keys())}")
                logger.info(f"[{self.worker_id}] [控制] 其他端：")
                for i in self.forward_connections.keys():
                    logger.info(f"[{self.worker_id}] {i}")
            
        finally:
            async with self.conn_lock:
                if type_id in self.control_connections:
                    try:
                        writer.close()
                        await writer.wait_closed()
                    except:
                        pass
                    finally:
                        if type_id in self.control_connections:
                            del self.control_connections[type_id]
                
                if type_id in self.forward_connections:
                    try:
                        f_writer = self.forward_connections[type_id][1]
                        f_writer.close()
                        await f_writer.wait_closed()
                    except:
                        pass
                    finally:
                        if type_id in self.forward_connections:
                            del self.forward_connections[type_id]

    async def auto_forward_heartbeat(self, types: list):
        # 其中一个链接关闭时另一个关闭
        while self.running:
            index = 0
            for forward_id in types:
                if forward_id in self.forward_connections:
                    index += 1
                    logger.info(f'[{self.worker_id}] auto_forward_heartbeat {forward_id}')
            
            logger.info(f'[{self.worker_id}] auto_forward_heartbeat {index} {len(types)}')
            if index != len(types):
                break

            await asyncio.sleep(2)
        
        for forward_id in types:
            try:
                if forward_id in self.forward_connections:
                    writer = self.forward_connections[forward_id][1]
                    writer.close()
                    await writer.wait_closed()
            except:
                pass
            finally:
                if forward_id in self.forward_connections:
                    del self.forward_connections[forward_id]

    async def forward(self, target_host_id, target_client_id):
        logger.info(f"[{self.worker_id}] [控制] 双端开始转发：")
        logger.info(f"[{self.worker_id}]       {target_host_id} <---> {target_client_id}")
        logger.info(f"[{self.worker_id}]                                   主机 <---> 客户端")

        logger.info(f"[{self.worker_id}] {self.forward_connections}")
        if target_client_id in self.forward_connections and target_host_id in self.forward_connections:
            logger.info(f'[{self.worker_id}] 开始转发')
            host_reader, host_writer = self.forward_connections[target_host_id]
            client_reader, client_writer = self.forward_connections[target_client_id]
            
            # 创建会话
            session_id = await self.session_manager.create_session(
                target_host_id, (host_reader, host_writer), 
                target_client_id, (client_reader, client_writer)
            )
            
            # 启动双向转发任务
            host_to_client = asyncio.create_task(
                self.forward_data(host_reader, host_writer, client_writer, "主机端", session_id)
            )
            client_to_host = asyncio.create_task(
                self.forward_data(client_reader, client_writer, host_writer, "客户端", session_id)
            )
            
            # 等待转发任务完成
            await asyncio.gather(host_to_client, client_to_host)
        
        else:
            logger.info(f'[{self.worker_id}] 不满足转发条件')

    async def handle_control_connection(self, reader, writer):
        """处理控制端连接（异步版本）"""
        addr = writer.get_extra_info('peername')
        type_id = None
        
        try:
            while self.running:
                try:
                    data = await reader.read(2048)
                    if not data:
                        logger.info(f"[{self.worker_id}] [控制] 连接 {addr} 关闭")
                        break
                    
                    response = data.decode('utf-8')
                    command = json.loads(response)
                except Exception as e:
                    logger.info(f"[{self.worker_id}] [控制] 错误 {e}")
                    break

                if not command.get('type') in ['host', 'client']:
                    logger.error(f"[{self.worker_id}] [控制] 连接 {addr} 不支持的类型")
                    writer.close()
                    await writer.wait_closed()
                    return
                
                action = command.get('action')
                if command.get('id', None) is None and action != "register_id":
                    logger.error(f"[{self.worker_id}] [控制] 连接 {addr} 缺失ID")
                    writer.close()
                    await writer.wait_closed()
                    return

                type_id = command.get('id', None)
                name = command.get('name')
                typec = command.get('type')
                
                if typec in ['client'] and action == "register_id":
                    """创建唯一临时ID
                    1. 主机端不需要请求获取ID，主机端是设置固定的
                    2. 客户端需要每次刷新或者每次新的连接 都需要拿到不同ID，某些情况 虽然关闭了连接请求，但TCP特性 会依然保持很短的时间，这段时间内 当前这个ID不可用，所有需要重新获取"""
                    new_id = await self.idgx.get_next_id(name)
                    writer.write(json.dumps({'register_id': new_id}).encode('utf-8'))
                    await writer.drain()
                    continue
                elif typec == 'host':
                    if action == "register":
                        # 身份验证等
                        async with self.conn_lock:
                            self.control_connections[type_id] = (reader, writer)
                            # 主机端需要维持在控制端的长连接
                            # asyncio.create_task(self.heartbeat(type_id, typec))
                            logger.info(f"[{self.worker_id}] [控制] 主机完成注册 {type_id}")
                    elif action == 'heartbeat':
                        writer.write(json.dumps({'action': 'heartbeat', 'id': type_id}).encode('utf-8'))
                        await writer.drain()
                    else:
                        logger.info(f"[{self.worker_id}] [控制] 主机{type_id}: 未知动作")
                elif typec == 'client':
                    target_host_id = command.get('target_host_id')
                    if action == "connect":
                        # 客户端请求与主机建立连接
                        async with self.conn_lock:
                            logger.info(f"[{self.worker_id}] [控制] 客户端{type_id}: 请求连接")
                            if target_host_id not in self.control_connections:
                                # 检查主机是否在线
                                logger.error(f"[{self.worker_id}] [控制] 客户端{type_id}: 主机 {target_host_id} 不在线")
                                writer.close()
                                await writer.wait_closed()
                                return
                            
                            host_reader, host_writer = self.control_connections[target_host_id]
                            self.control_connections[type_id] = (reader, writer)

                            # 通知主机端有新客户端连接
                            host_writer.write(json.dumps({
                                "id": target_host_id,
                                "type": 'client',
                                "target_client_id": type_id,
                                "forward_port": self.forward_port
                            }).encode('utf-8'))
                            await host_writer.drain()
                            logger.info(f"[{self.worker_id}] [控制] 通知主机{target_host_id}: 建立数据通道")
                            
                            # 通知客户端开始连接数据端口
                            writer.write(json.dumps({
                                "id": type_id,
                                "type": 'host',
                                "target_host_id": target_host_id,
                                "forward_port": self.forward_port
                            }).encode('utf-8'))
                            await writer.drain()
                            logger.info(f"[{self.worker_id}] [控制] 通知客户{type_id}: 建立数据通道")
                            
                            # asyncio.create_task(self.heartbeat(type_id, typec))
                            logger.info(f"[{self.worker_id}] [控制] 客户端{type_id}: 连接已建立")
                    elif action == "forward":
                        target_host_id = command.get('target_host_id')
                        logger.info(f"[{self.worker_id}] 开始转发: {target_host_id} -> {type_id}")
                        await self.forward(target_host_id, type_id)
                    elif action == 'heartbeat':
                        writer.write(json.dumps({'type': 'heartbeat', 'id': type_id}).encode('utf-8'))
                        await writer.drain()
                    elif action == 'multicast':
                        # 客户端广播MOTD数据
                        writer.write(json.dumps({'type': 'multicast', 'id': type_id, 'message': 'BUGG测试联机'}).encode('utf-8'))
                        await writer.drain()
                    else:
                        logger.info(f"[{self.worker_id}] [控制] 客户端{type_id}: 未知动作")
        except Exception as e:
            logger.error(f"[{self.worker_id}] 处理主机{addr} 连接错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            try:
                if type_id is None:
                    return
                
                async with self.conn_lock:
                    if type_id in self.control_connections:
                        try:
                            _, writer = self.control_connections[type_id]
                            writer.close()
                            await writer.wait_closed()
                        except:
                            pass
                        finally:
                            if type_id in self.control_connections:
                                del self.control_connections[type_id]
                    
                    if type_id in self.forward_connections:
                        try:
                            _, writer = self.forward_connections[type_id]
                            writer.close()
                            await writer.wait_closed()
                        except:
                            pass
                        finally:
                            if type_id in self.forward_connections:
                                del self.forward_connections[type_id]
            except:
                pass

    async def handle_forward_connection(self, reader, writer):
        """处理数据端连接（异步版本）"""
        addr = writer.get_extra_info('peername')
        
        try:
            # 读取客户端ID和目标主机ID
            data = await reader.read(2048)
            if not data:
                writer.close()
                await writer.wait_closed()
                return
                
            response = data.decode('utf-8')
            command = json.loads(response)

            if not command.get('type') in ['host', 'client']:
                logger.error(f"[{self.worker_id}] [数据] 连接 {addr} 不支持的类型")
                writer.close()
                await writer.wait_closed()
                return
            
            if command.get('id', None) is None:
                logger.error(f"[{self.worker_id}] [数据] 连接 {addr} 缺失ID")
                writer.close()
                await writer.wait_closed()
                return

            type_id = command.get('id', None)
            typec = command.get('type')

            if typec == 'host':
                # 需要交叉验证 是否在控制端完成注册
                async with self.conn_lock:
                    if type_id not in self.control_connections:
                        logger.error(f"[{self.worker_id}] [数据] 控制端中不存在 {type_id} 主机")
                        writer.close()
                        await writer.wait_closed()
                        return
                    
                    target_client_id = command.get('target_client_id')
                    if not target_client_id:
                        logger.error(f"[{self.worker_id}] [数据] 主机未提供有效的客户端ID")
                        writer.close()
                        await writer.wait_closed()
                        return
                    
                    if target_client_id not in self.control_connections:
                        logger.error(f"[{self.worker_id}] [数据] 控制端中不存在 {target_client_id} 客户端")
                        writer.close()
                        await writer.wait_closed()
                        return

                    self.forward_connections[type_id] = (reader, writer)
                
                logger.info(f"[{self.worker_id}] [数据] 主机端 {type_id} 已建立数据端口的连接")

            elif typec == 'client':
                # 需要交叉验证 是否在控制端完成注册
                async with self.conn_lock:
                    if type_id not in self.control_connections:
                        logger.error(f"[{self.worker_id}] [数据] 控制端中不存在 {type_id} 客户端")
                        writer.close()
                        await writer.wait_closed()
                        return
                    
                    target_host_id = command.get('target_host_id')
                    if not target_host_id:
                        logger.error(f"[{self.worker_id}] [数据] 客户端未提供有效的主机ID")
                        writer.close()
                        await writer.wait_closed()
                        return

                    # 检查主机是否在线
                    if target_host_id not in self.control_connections:
                        logger.error(f"[{self.worker_id}] [数据] 客户端{type_id}: 主机 {target_host_id} 不在线")
                        writer.close()
                        await writer.wait_closed()
                        return

                    self.forward_connections[type_id] = (reader, writer)
                
                logger.info(f"[{self.worker_id}] [数据] 客户端 {type_id} 已建立数据端口的连接")

        except Exception as e:
            logger.error(f"[{self.worker_id}] 处理客户端{addr} 连接错误: {e}")

    async def start_control_server(self):
        """启动控制端服务（异步版本）"""
        self.control_server = await asyncio.start_server(
            self.handle_control_connection,
            self.host, self.control_port,
            reuse_address=True,
            reuse_port=True,
            backlog=100
        )
        
        logger.info(f"[{self.worker_id}] [控制] 服务监听在 {self.host}:{self.control_port}")
        
        async with self.control_server:
            await self.control_server.serve_forever()

    async def start_forward_server(self):
        """启动数据端服务（异步版本）"""
        self.forward_server = await asyncio.start_server(
            self.handle_forward_connection,
            self.host, self.forward_port,
            reuse_address=True,
            reuse_port=True,
            backlog=100
        )

        logger.info(f"[{self.worker_id}] [数据] 数据端服务监听在 {self.host}:{self.forward_port}")
        
        async with self.forward_server:
            await self.forward_server.serve_forever()

    async def start(self):
        """启动服务器（异步版本）"""
        # 设置信号处理
        self._setup_signal_handlers()

        logger.info(f"[{self.worker_id}] 启动隧道服务器")
        
        # 启动控制端和数据端服务
        control_task = asyncio.create_task(self.start_control_server())
        forward_task = asyncio.create_task(self.start_forward_server())
        
        try:
            # 等待服务器任务
            await asyncio.gather(control_task, forward_task)
        except asyncio.CancelledError:
            logger.info(f"[{self.worker_id}] 服务器任务被取消")
        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"[{self.worker_id}] 服务器错误: {e}")
        finally:
            await self.shutdown()

    async def shutdown(self):
        """关闭服务器（异步版本）"""
        self.running = False
        logger.info(f"[{self.worker_id}] 正在关闭服务器...")
        
        # 关闭所有连接
        async with self.conn_lock:
            # 关闭控制连接
            for type_id, (reader, writer) in list(self.control_connections.items()):
                try:
                    writer.close()
                    await writer.wait_closed()
                except:
                    pass
            self.control_connections.clear()
            
            # 关闭数据连接
            for type_id, (reader, writer) in list(self.forward_connections.items()):
                try:
                    writer.close()
                    await writer.wait_closed()
                except:
                    pass
            self.forward_connections.clear()
        
        # 关闭服务器
        if self.control_server:
            self.control_server.close()
            await self.control_server.wait_closed()
        if self.forward_server:
            self.forward_server.close()
            await self.forward_server.wait_closed()
        
        logger.info(f"[{self.worker_id}] 服务器关闭完成")


async def main():
    server = TunnelServer(host='0.0.0.0', control_port=3333, forward_port=3334)
    await server.start()

if __name__ == '__main__':
    asyncio.run(main())
