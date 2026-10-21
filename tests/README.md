# 服务端测试

本目录是 unittest 测试套件，不依赖已部署节点，也不要求启动器正在运行。测试使用临时目录、随机空闲端口和本机服务；不会使用 `config/remote-test` 的服务器或凭据。

## 独立服务端回归

在仓库根目录安装 `requirements.txt`，使用同一个 Python 执行：

```sh
python -X utf8 -m unittest discover -s tests -p "test_*.py" -v
```

使用 venv 时换为 `.venv/bin/python` 或 `.venv\Scripts\python.exe`。失败通过 unittest 的异常、断言和非零退出码报告；CI 在 Windows 和 Linux 上运行同一命令。

|测试文件|主要行为与失败路径|
|---|---|
|`test_node_startup.py`|配置/公钥/证书一致、拒绝覆盖密钥、无效地址端口、代理入口、缺配置退出、实际 HTTPS 和 SSH 启动及关闭释放端口|
|`test_relay_security.py`|错误 token/角色/房间密钥、公钥不匹配、禁止 shell/exec/SFTP、目录越权、任意转发、超长帧、关闭后的旧凭据|
|`test_capacity.py`|人数计数、并发准入、跨房间带宽预算、容量调整、房主上报游戏人数及过期、真实双向转发字节|
|`test_heartbeat.py`|后台多节点发现、SSH 配置隔离、局部失败后继续同步|
|`test_federation_integrity.py`|签名/网络证明篡改、旧心跳重放、过期/未来公告、目录大小限制、房间归属冲突、本地屏蔽范围|
|`test_account_replication.py`|四节点真实 SSH 同步、公开目录与密文分离、指定副本数、非副本路由、注册/副本节点故障补位、撤回副本、签名策略篡改、重名与重启恢复|
|`test_portal_governance.py`|公开页面与受保护数据分离、CSRF、再次鉴权、本地隔离/恢复/审计、后台路由、SMTP 设置脱敏、邮件要求、公开接入示例及错误公钥|
|`test_mail.py`|验证码绑定、一次性消费、过期/重放/限速、HTML 转义、秘密不进入邮件或错误、先 STARTTLS 后认证|
|`test_peer_signaling_stun.py`|房间内信令角色、跨房间隔离、坏帧、STUN IPv4/IPv6 编码、畸形包和来源限流|
|`test_peer_wire.py`|真实 SSH 信令往返及防身份冒用、拒绝目录身份信令、真实 UDP Binding 源端口/事务号验证|

新增行为应补正常、拒绝和清理路径，并断言可观察的结果。网络数据测试比较真实载荷；协议测试检查返回、状态变化及资源释放，不以打印 PASS、调用次数或常量相等代替结果。

## 启动器协议与 P2P 集成

服务端负责 STUN 和房间内信令；ICE、DTLS/SCTP 与本机游戏端口由启动器连接组件实现，因此完整 P2P 用例在 `buggcraft/tests/test_peer_transport.py`，标准接口用例在 `test_bridge_protocol.py`。

将启动器源码放在相邻的 `buggcraft/`，安装其测试所需依赖后，从节点仓库运行：

```sh
python deploy/check_server.py
```

该命令先运行本仓库 unittest，再运行启动器里的账号、网页、联邦、聊天、房间生命周期、游戏状态、P2P 和 JSON-RPC 用例；缺少启动器时明确失败。可以用 `--launcher PATH` 指定位置，或 `--native-only` 仅运行服务端套件。

只复测 P2P 和标准桥接时，在启动器仓库执行：

```sh
python -X utf8 -m unittest -v tests.test_peer_transport tests.test_bridge_protocol
```

这些用例验证实际加密直连与兆字节数据、并行流、EOF、禁止中转时的直连、同房间混合路径、协商失败/超时后的中转、新连接在直连中断后的回退，以及独立 JSON-RPC 子进程的创建/加入/关闭。创建 ICE 失败和丢失 offer 的场景使用故障注入，不能称作真实运营商 UDP 阻断测试。

**本机 ICE 直连、STUN 返回地址均不等于真实公网 NAT 打洞验收。** 还需要两台位于不同网络的客户端，分别记录实际选中候选对、直连数据和节点中转字节，并覆盖家庭 NAT、双重/对称 NAT、IPv6、UDP 被阻断、仅中继和同房间混合路径。不能直连的环境应稳定回退；任何未执行的网络组合都不能标记通过。

## 可选本地验收工具

下列工具需要先启动本机四节点，不属于 unittest 用例，也不要对生产数据运行。全部从节点仓库根目录执行：

```sh
python deploy/local_cluster.py
# 另一个终端
python deploy/check_cluster.py --clients 5 --report config/local-cluster/transport-results.json
```

默认启动 SSH 34331–34334 和 HTTPS 18443–18446。`check_cluster.py` 使用相邻启动器 SDK，默认创建四个房间、20 个访客，校验 40 MiB 双向载荷及聊天隔离。它测试传输，不代表真实游戏人数、带宽峰值或公网打洞。

网页交互验收另外需要 Playwright 和 Chromium，及相邻的启动器 SDK：

```sh
python -m pip install playwright
python -m playwright install chromium
python deploy/check_accounts_web.py
python deploy/check_capacity_web.py --directory config/local-cluster/A --web-port 18443
python deploy/check_console_web.py --directory config/local-cluster/A --web-port 18443
```

账号验收会创建测试账号并改变注册设置；容量验收临时调整并恢复容量；后台验收会临时隔离/恢复一个成员并留下本地操作记录。它们只用于可丢弃的本地集群。参数以各工具 `--help` 为准；浏览器截图/报告默认写到相邻 `multiplayer-tests/`，不能包含账号密钥或接入码。
