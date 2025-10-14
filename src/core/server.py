import asyncio
import logging
import time
from typing import Dict, List, Optional
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor

from network.connection import ConnectionManager, TunnelConnection
from discovery.registry import ServiceRegistry
from loadbalancer.manager import LoadBalancerManager
from monitor.metrics import MetricsCollector


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        # self.logger.FileHandler("tunnel_host.log"),
        logging.StreamHandler()
    ]
)



class TunnelServer:
    """高性能隧道服务器"""

    def __init__(self, config: Dict):
        self.config = config
        self.running = False
        self.workers: List[mp.Process] = []
        self.logger = logging.getLogger("TunnelServer")
        # 核心组件
        self.connection_manager = ConnectionManager(config)
        self.service_registry = ServiceRegistry(config)
        self.load_balancer = LoadBalancerManager(config)
        self.metrics = MetricsCollector()
        
        # 异步任务
        self.tasks: List[asyncio.Task] = []
        self.worker_restart_attempts: Dict[int, int] = {}  # 记录工作进程重启次数
    
    async def start(self):
        """启动服务器"""
        self.logger.info("Starting tunnel server...")
        self.running = True
        
        # 启动核心组件
        await self.service_registry.start()
        await self.load_balancer.start()
        
        # 启动工作进程
        await self._start_worker_processes()
        
        # 启动监控任务
        self.tasks.extend([
            asyncio.create_task(self._monitor_loop()),
            asyncio.create_task(self._health_check_loop()),
            asyncio.create_task(self._metrics_report_loop())
        ])
        
        self.logger.info("Tunnel server started successfully")
        
        # 等待服务器停止
        while self.running:
            await asyncio.sleep(1)
    
    async def stop(self):
        """停止服务器"""
        self.logger.info("Stopping tunnel server...")
        self.running = False
        
        # 取消所有任务
        for task in self.tasks:
            task.cancel()
        
        # 等待任务完成或取消
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        # 停止工作进程
        for worker in self.workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=5)
                if worker.is_alive():
                    self.logger.warning(f"Worker {worker.name} did not terminate gracefully")
        
        # 停止核心组件
        try:
            await self.load_balancer.stop()
        except Exception as e:
            self.logger.error(f"Error stopping load balancer: {e}")
        
        try:
            await self.service_registry.stop()
        except Exception as e:
            self.logger.error(f"Error stopping service registry: {e}")
        
        self.logger.info("Tunnel server stopped successfully")

    async def _start_worker_processes(self):
        """启动工作进程"""
        worker_count = mp.cpu_count()
        worker = self.config.get('server', {}).get('worker_processes', 'auto')
        if worker != 'auto':
            worker_count = int(worker)
        
        for i in range(worker_count):
            worker = mp.Process(
                target=worker_main,
                args=(i, self.config),
                name=f"TunnelWorker-{i}"
            )
            worker.start()
            self.workers.append(worker)
            self.logger.info(f"Started worker process {i}")
    
    async def _monitor_loop(self):
        """监控循环 - 完整实现"""
        while self.running:
            try:
                # 检查工作进程状态
                active_workers = 0
                for i, worker in enumerate(self.workers):
                    if worker.is_alive():
                        active_workers += 1
                    else:
                        self.logger.warning(f"Worker {i} died, restarting...")
                        # 重启工作进程
                        await self._restart_worker(i)
                
                # 更新活跃工作进程数指标
                self.metrics.record('active_workers', active_workers)
                
                # 检查系统资源
                await self._check_system_resources()
                
                # 记录监控周期
                self.metrics.increment('monitor_cycles')
                
                await asyncio.sleep(5)  # 5秒检查一次
                
            except Exception as e:
                self.logger.error(f"Monitor error: {e}")
                self.metrics.increment('monitor_errors')
                await asyncio.sleep(5)  # 出错时也等待5秒

    async def _health_check_loop(self):
        """健康检查循环 - 完整实现"""
        while self.running:
            try:
                # 执行服务注册中心的健康检查
                registry_health = await self.service_registry.health_check()
                self.metrics.record_health_status(registry_health)
                
                # 执行负载均衡器的健康检查
                lb_health = await self.load_balancer.health_check()
                self.metrics.record('load_balancer_health', lb_health)
                
                # 执行连接管理器的健康检查
                conn_health = self.connection_manager.health_check()
                self.metrics.record('connection_manager_health', conn_health)
                
                # 记录健康检查周期
                self.metrics.increment('health_checks')
                
                # 如果整体不健康，记录警告
                if not self.metrics.is_healthy():
                    self.logger.warning("System health check failed")
                
                await asyncio.sleep(30)  # 30秒检查一次
                
            except Exception as e:
                self.logger.error(f"Health check error: {e}")
                self.metrics.increment('health_check_errors')
                await asyncio.sleep(30)  # 出错时也等待30秒
    
    async def _metrics_report_loop(self):
        """指标上报循环 - 完整实现"""
        while self.running:
            try:
                # 收集指标
                metrics = self.metrics.collect()
                
                # 添加系统特定指标
                metrics.update({
                    'worker_processes': len(self.workers),
                    'active_worker_processes': len([w for w in self.workers if w.is_alive()]),
                    'system_time': time.time()
                })
                
                # 上报指标
                await self._report_metrics(metrics)
                
                # 记录上报周期
                self.metrics.increment('metric_reports')
                
                await asyncio.sleep(60)  # 60秒上报一次
                
            except Exception as e:
                self.logger.error(f"Metrics report error: {e}")
                self.metrics.increment('metric_report_errors')
                await asyncio.sleep(60)  # 出错时也等待60秒

    async def _check_system_resources(self):
        """检查系统资源使用情况"""
        try:
            import psutil
            
            # 获取CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)
            self.metrics.record('cpu_percent', cpu_percent)
            
            # 获取内存使用情况
            memory = psutil.virtual_memory()
            self.metrics.record('memory_percent', memory.percent)
            self.metrics.record('memory_used_mb', memory.used // 1024 // 1024)
            
            # 获取磁盘使用情况（如果有相关路径）
            disk = psutil.disk_usage('/')
            self.metrics.record('disk_percent', disk.percent)
            
            # 获取网络IO（如果可能）
            net_io = psutil.net_io_counters()
            if net_io:
                self.metrics.record('net_bytes_sent', net_io.bytes_sent)
                self.metrics.record('net_bytes_recv', net_io.bytes_recv)
            
            # 如果资源使用过高，记录警告
            if cpu_percent > 80:
                self.logger.warning(f"High CPU usage: {cpu_percent}%")
            if memory.percent > 80:
                self.logger.warning(f"High memory usage: {memory.percent}%")
                
        except ImportError:
            self.logger.debug("psutil not available, skipping system resource check")
        except Exception as e:
            self.logger.error(f"Error checking system resources: {e}")

    async def graceful_shutdown(self):
        """优雅关闭"""
        self.logger.info("Starting graceful shutdown...")
        self.running = False
        
        # 取消所有任务
        for task in self.tasks:
            task.cancel()
        
        # 停止工作进程
        for worker in self.workers:
            if worker.is_alive():
                worker.terminate()
        
        # 停止核心组件
        await self.load_balancer.stop()
        await self.service_registry.stop()
        
        self.logger.info("Tunnel server stopped")

    async def _restart_worker(self, worker_index: int):
        """重启工作进程"""
        worker_id = f"worker-{worker_index}"
        
        # 检查重启次数，避免无限重启
        restart_count = self.worker_restart_attempts.get(worker_index, 0)
        if restart_count >= 3:  # 最多重启3次
            self.logger.error(f"Worker {worker_index} has been restarted {restart_count} times, giving up")
            return
        
        try:
            # 清理旧进程（如果存在）
            if worker_index < len(self.workers) and self.workers[worker_index].is_alive():
                self.workers[worker_index].terminate()
                self.workers[worker_index].join(timeout=5)
            
            # 创建新工作进程
            new_worker = mp.Process(
                target=worker_main,
                args=(worker_index, self.config),
                name=f"TunnelWorker-{worker_index}-restart-{restart_count + 1}"
            )
            new_worker.start()
            
            # 更新进程列表
            if worker_index < len(self.workers):
                self.workers[worker_index] = new_worker
            else:
                self.workers.append(new_worker)
            
            # 记录重启次数
            self.worker_restart_attempts[worker_index] = restart_count + 1
            
            self.logger.info(f"Successfully restarted worker {worker_index} (attempt {restart_count + 1})")
            
            # 等待进程启动完成
            await asyncio.sleep(1)
            
        except Exception as e:
            self.logger.error(f"Failed to restart worker {worker_index}: {e}")
            self.worker_restart_attempts[worker_index] = restart_count + 1
    
    async def _report_metrics(self, metrics: Dict):
        """上报监控指标"""
        try:
            # 这里可以实现多种上报方式：
            # 1. 写入日志文件
            # 2. 发送到监控系统（如Prometheus）
            # 3. 发送到消息队列
            # 4. 存储到数据库
            
            # 当前实现：记录到日志和性能文件
            metrics_log = {
                'timestamp': time.time(),
                'connections': metrics.get('connections', 0),
                'bytes_received': metrics.get('bytes_received', 0),
                'bytes_sent': metrics.get('bytes_sent', 0),
                'active_sessions': metrics.get('active_sessions', 0),
                'uptime': metrics.get('uptime', 0),
                'worker_count': len([w for w in self.workers if w.is_alive()])
            }
            
            # 记录到结构化日志
            self.logger.info("Metrics report", extra={'metrics': metrics_log})
            
            # 写入性能日志文件
            await self._write_performance_log(metrics_log)
            
            # 如果启用了外部监控，可以在这里添加
            if self.config.get('monitoring', {}).get('external_enabled', False):
                await self._send_to_external_monitor(metrics_log)
                
        except Exception as e:
            self.logger.error(f"Error reporting metrics: {e}")
    
    async def _write_performance_log(self, metrics: Dict):
        """写入性能日志文件"""
        try:
            log_entry = f"{time.strftime('%Y-%m-%d %H:%M:%S')} - " \
                       f"Connections: {metrics['connections']}, " \
                       f"RX: {metrics['bytes_received']} bytes, " \
                       f"TX: {metrics['bytes_sent']} bytes, " \
                       f"Uptime: {metrics['uptime']:.2f}s\n"
            
            # 异步写入文件
            log_file = self.config.get('monitoring', {}).get('performance_log', 'logs/performance.log')
            with open(log_file, 'a') as f:
                f.write(log_entry)
                
        except Exception as e:
            self.logger.error(f"Error writing performance log: {e}")
    
    async def _send_to_external_monitor(self, metrics: Dict):
        """发送到外部监控系统"""
        # 这里可以实现发送到Prometheus、StatsD、Datadog等监控系统
        # 示例：发送到HTTP端点
        try:
            monitor_url = self.config.get('monitoring', {}).get('external_url')
            if monitor_url:
                # 使用aiohttp发送HTTP请求
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.post(monitor_url, json=metrics) as response:
                        if response.status != 200:
                            self.logger.warning(f"External monitor returned status {response.status}")
        except ImportError:
            self.logger.warning("aiohttp not available, skipping external monitoring")
        except Exception as e:
            self.logger.error(f"Error sending to external monitor: {e}")


def worker_main(worker_id: int, config: Dict):
    """工作进程主函数"""
    # 工作进程有自己的事件循环和服务器实例
    logger = logging.getLogger("Main")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        worker = TunnelWorker(worker_id, config)
        loop.run_until_complete(worker.run())
    except Exception as e:
        logger.error(f"Worker {worker_id} error: {e}")
    finally:
        loop.close()


class TunnelWorker:
    """隧道工作进程"""
    
    def __init__(self, worker_id: int, config: Dict):
        self.worker_id = worker_id
        self.config = config
        self.server_socket = None
        self.connections = {}
        self.logger = logging.getLogger("TunnelWorker")
        
    async def run(self):
        """运行工作进程"""
        self.logger.info(f"Worker {self.worker_id} starting...")
        
        # 创建服务器socket
        self.server_socket = await self._create_server_socket()
        
        # 启动事件循环
        await self._event_loop()
    
    async def _create_server_socket(self):
        """创建服务器socket"""
        # 配置服务器选项
        server_options = {
            'host': self.config['server']['host'],
            'port': int(self.config['server']['port']),
            'reuse_address': True,
            'reuse_port': False,  #not self.is_windows,  # Windows不支持SO_REUSEPORT
            'backlog': 1000,  # self.max_connections,
            'start_serving': True
        }
        
        # 创建服务器
        return await asyncio.start_server(
            self.handle_client,
            **server_options
        )

    async def handle_client(self, reader: asyncio.StreamReader, 
                          writer: asyncio.StreamWriter):
        """处理客户端连接"""
        connection_id = id(writer)
        client_addr = writer.get_extra_info('peername')
        
        self.logger.info(f"Worker {self.worker_id}: New connection from {client_addr}")
        
        # 创建连接对象
        connection = TunnelConnection(connection_id, reader, writer, client_addr)
        self.connections[connection_id] = connection
        
        try:
            # 处理连接生命周期
            await connection.handle()
        except Exception as e:
            self.logger.error(f"Connection {connection_id} error: {e}")
        finally:
            # 清理连接
            if connection_id in self.connections:
                del self.connections[connection_id]
            writer.close()
            await writer.wait_closed()
    
    async def _event_loop(self):
        """事件循环"""
        # 这里可以添加其他周期性任务
        while True:
            await asyncio.sleep(1)
