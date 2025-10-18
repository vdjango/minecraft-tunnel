class TunnelError(Exception):
    """隧道错误基类"""
    pass

class HandshakeError(TunnelError):
    """握手协议错误"""
    pass

class ConnectionClosedError(TunnelError):
    """连接被客户端关闭"""
    pass

class AuthenticationError(TunnelError):
    """认证错误"""
    pass

class ProtocolError(TunnelError):
    """协议错误"""
    pass
