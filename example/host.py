# tunnel_host.py
import json
import socket
import threading
import logging
import sys
import signal
import struct

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("tunnel_host.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("TunnelHost")

def signal_handler(sig, frame):
    logger.info("检测到Ctrl+C，程序正在退出...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)


class TunnelHost:
    def __init__(self, router_host='127.0.0.1', router_port=3000,
                 game_host='127.0.0.1', game_port=25565, host_id=1):
        self.router_host = router_host
        self.router_port = router_port
        self.game_host = game_host
        self.game_port = game_port
        self.host_id = host_id
        self.running = True

        # 路由信息
        self.worker_host = None
        self.worker_control_port = None
        self.worker_forward_port = None
        # self.worker_id = None

        self.send_data = {
            "id": self.host_id,
            "name": self.host_id,                   # 主机唯一ID
            "type": 'host',                         # 当前为主机
        }
        
        self.control_conn = None
        self.active_sessions = {}  # client_id -> (game_conn, server_conn)

    def query_router(self):
        """查询路由服务器获取工作进程信息（同步版本）"""
        try:
            # 连接到路由服务器
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)  # 10秒超时
            sock.connect((self.router_host, self.router_port))
            
            # 发送注册请求
            register_request = {
                'action': 'register',
                'host_id': self.host_id
            }
            
            sock.sendall(json.dumps(register_request).encode())
            
            # 读取路由响应
            response_data = sock.recv(1024)
            sock.close()
            
            response = json.loads(response_data.decode())
            print(response)
            if response.get('status') != 'success':
                logger.error(f"路由注册失败: {response.get('error')}")
                return False
            
            # 保存工作进程信息
            self.worker_host = response.get('host', 'localhost')
            self.worker_control_port = response.get('control_port')
            self.worker_forward_port = response.get('forward_port')
            # self.worker_id = response.get('worker_id')
            
            logger.info(f"路由注册成功: 主机 {self.host_id}")
            logger.info(f"工作进程地址: {self.worker_host}:{self.worker_control_port}(控制) {self.worker_forward_port}(数据)")
            return True
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"路由查询错误: {e}")
            return False

    def control_connection(self):
        """连接到工作进程控制端"""
        if not self.worker_host or not self.worker_control_port:
            logger.error("未获取到工作进程信息，请先查询路由")
            return None
            
        logger.info(f'连接到控制端 {self.worker_host}:{self.worker_control_port}')
        control_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        control_conn.settimeout(50)
        control_conn.connect((self.worker_host, self.worker_control_port))
        return control_conn

    def create_forward_session(self, control, target_client_id, port):
        """与服务端数据端口建立连接进行数据转发路由"""
        # 连接到游戏服务器
        game_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        game_conn.connect((self.game_host, self.game_port))
        logger.info(f"客户端会话{target_client_id}: 已连接到游戏服务器")

        # 连接到服务端的数据端口
        data_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        data_conn.connect((self.worker_host, port))  # 数据端口

        # 发送通知到数据端口，告知服务端主机端准备已就绪，要开始转发数据
        data_conn.sendall(json.dumps({
            **self.send_data,
            "target_client_id": target_client_id
        }).encode('utf-8'))
        logger.info(f"主机端已连接到数据端")
        
        # 启动双向转发
        def forward_game_to_server():
            try:
                while True:
                    data = game_conn.recv(4096)
                    if not data:
                        break
                    data_conn.send(data)
            except:
                pass
        
        def forward_server_to_game():
            try:
                while True:
                    data = data_conn.recv(4096)
                    if not data:
                        break
                    game_conn.send(data)
            except:
                pass
        
        t1 = threading.Thread(target=forward_game_to_server, daemon=True)
        t2 = threading.Thread(target=forward_server_to_game, daemon=True)
        t1.start()
        t2.start()
        
        t1.join()
        t2.join()
        
        data_conn.close()
        game_conn.close()
        logger.info(f"主机端已与数据端关闭")

    def start(self):
        """启动主机端"""
        # 首先查询路由服务器
        if not self.query_router():
            logger.error("无法获取路由信息，主机启动失败")
            return
            
        try:
            # 连接到控制端
            self.control_conn = self.control_connection()
            if not self.control_conn:
                return
            
            # 发送主机端标识及主机端ID 进行平台注册
            self.control_conn.sendall(json.dumps({
                **self.send_data,
                "action": "register"    # 主机请求与服务端控制端进行平台注册
            }).encode('utf-8'))

            logger.info(f"主机 {self.send_data['id']} 已连接到控制端，等待客户端连接...")
            while self.running:
                try:
                    # 等待新客户端连接通知
                    data = self.control_conn.recv(2048)
                    if not data:
                        break
                    
                    command = json.loads(data.decode('utf-8'))
                    if command.get('type') == 'heartbeat':
                        # 心跳包
                        continue

                    if not command.get('type') in ['client', 'heartbeat']:
                        logger.error(f"[主机] 收到不支持的客户端连接请求类型 {command.get('type')}")
                        self.control_conn.close()
                        return
                    
                    if command.get('id', None) is None:
                        logger.error(f"[主机] 未提供主机端ID")
                        self.control_conn.close()
                        return
                    
                    if command.get('id', None) != self.send_data['id']:
                        logger.error(f"[主机] 客户端请求目标主机不匹配，貌似是路由错误")
                        self.control_conn.close()
                        return
                    
                    if command.get('target_client_id', None) is None:
                        logger.error(f"[主机] 未提供客户端ID")
                        self.control_conn.close()
                        return
                    
                    if command.get('forward_port', None) is None:
                        logger.error(f"[主机] 服务端未提供数据端口")
                        self.control_conn.close()
                        return
                    
                    # 客户端唯一ID
                    # 服务端提供的数据端口，主机需要与此端口建立连接进行数据交换
                    target_client_id = command.get('target_client_id')
                    forward_port = command.get('forward_port')

                    threading.Thread(
                        target=self.create_forward_session, daemon=True,
                        args=(self.control_conn, target_client_id, forward_port)
                    ).start()

                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"接收数据错误: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"连接服务端失败: {e}")
        finally:
            self.shutdown()

    def shutdown(self):
        """关闭主机端"""
        self.running = False
        if self.control_conn:
            try:
                self.control_conn.close()
            except:
                pass
        logger.info("主机端已关闭")

# 使用示例
if __name__ == '__main__':
    host = TunnelHost(
        router_host='127.0.0.1',  # 路由服务器地址
        router_port=3000,         # 路由服务器端口
        game_host='127.0.0.1',    # 游戏服务器地址
        game_port=25565,          # 游戏服务器端口
        host_id='7bee17e09c5a539cba34d35b885d13f7'  # 主机唯一ID
    )
    host.start()