# 服务端测试

本目录是 unittest 套件，使用临时目录、随机端口和本机服务，不需要预先部署节点，也不访问 `config/remote-test` 的服务器或凭据。安装 `requirements.txt` 后在仓库根目录执行：

```sh
python -X utf8 -m unittest discover -s tests -p "test_*.py" -v
```

CI 在 Windows 和 Linux 上执行同一命令。失败通过实际异常、断言和非零退出码报告。

|测试文件|覆盖行为|
|---|---|
|`test_onboarding.py`|真实 HTTPS 向导、缺失/错误口令、跨站拒绝、无效配置、端口占用、密码哈希、容量持久化、并发/重复提交拒绝、写盘失败清理重试、向导自动切换节点、重启不重新初始化|
|`test_node_startup.py`|配置/公钥/证书一致、拒绝覆盖密钥、非法地址端口、代理入口、缺配置退出、实际 HTTPS 和 SSH 启动与关闭释放端口|
|`test_service_installation.py`|无第三方依赖的安装入口、独立环境命令、只复制运行文件、依赖失败保持旧版本、拒绝覆盖其他服务、版本切换与启动失败回滚（链接相关用例在 Linux 执行）|
|`test_systemd_service.py`|隔离 Linux 主机上的实际服务安装、HTTPS 初始化、非 root 数据权限、开机启动配置、systemctl 重启、二次安装保留身份|
|`test_relay_security.py`|错误 token/角色/房间密钥、公钥不匹配、禁止 shell/exec/SFTP、目录越权、任意转发、超长帧、失效凭据|
|`test_capacity.py`|人数计数、并发准入、跨房间预算、容量调整、游戏人数与过期、真实双向转发字节|
|`test_bandwidth.py`|服务器收发速率、实际采样间隔、多网卡合计、回环排除、计数重置/网卡增删、读取失败恢复、过期和后台任务清理|
|`test_portable_package.py`|对真实 PyInstaller 发行目录的首次向导、HTTPS 指纹、协议页、管理员登录、SSH 监听、重启保留身份、无关工作目录和故障系统日志（需设置 `BUGGCRAFT_TEST_PACKAGE`）|
|`test_heartbeat.py`|多节点发现、SSH 配置隔离、部分节点失败后继续同步|
|`test_federation_integrity.py`|签名/网络证明篡改、心跳重放、过期/未来公告、大小限制、房间归属冲突、本地隔离范围|
|`test_account_replication.py`|四节点实际 SSH 同步、目录与密文分离、副本数、非副本路由、故障补位、撤回副本、策略篡改、重名及重启恢复|
|`test_portal_governance.py`|公开/受保护页面、CSRF、再次鉴权、本地隔离/恢复/审计、后台路由、SMTP 脱敏、同页协议和接入示例、错误公钥|
|`test_mail.py`|验证码绑定/消费/过期/重放/限速、HTML 转义、敏感数据不进入邮件或错误、STARTTLS 后认证|
|`test_registration_browser.py`|真实 HTTPS 网页的输入校验、慢发信等待状态、SMTP 拒绝提示与重试、重发倒计时、网络失败恢复、实际加密注册/恢复文件下载/登录/个人接入码；只替换 SMTP 发送，账号接口和加密均真实执行|
|`test_peer_signaling_stun.py`|房间信令角色、跨房间隔离、坏帧、STUN IPv4/IPv6、畸形包和来源限流|
|`test_peer_wire.py`|真实 SSH 信令与防冒用、拒绝目录身份信令、实际 UDP Binding 源端口/事务号验证|

新增功能需补正常、拒绝、清理路径，并断言可观察结果。网络数据比较实际载荷；权限检查返回和状态变化；不能以打印 PASS 或常量相等代替功能测试。已删除 `deploy` 中依赖事先运行环境的验收脚本，正式回归由本目录用例负责。

## 客户端 P2P 与标准接入

节点负责 STUN 和信令；ICE、DTLS/SCTP 与本地游戏端口由启动器连接组件负责。相邻启动器仓库安装依赖后，在其根目录运行：

```sh
python -X utf8 -m unittest -v tests.test_peer_transport tests.test_bridge_protocol
```

这些用例验证本机实际加密直连与兆字节载荷、并行流、EOF、禁止中转时的直连、同房间混合路径、协商失败/超时后的中转、直连中断后的新连接回退，以及 JSON-RPC 子进程的创建/加入/关闭。创建 ICE 失败和丢失 offer 使用故障注入，不能称为实际运营商 UDP 阻断测试。

本机 ICE 直连、STUN 返回地址不等于跨公网 NAT 打洞验收。还需要两台不同网络的客户端，记录实际候选对、数据路径和中转字节，覆盖家庭 NAT、双重/对称 NAT、IPv6、UDP 被阻断、只中转和同房间混合路径。未执行的组合不能标记通过。

## 网页与部署验收

`test_deployed_nodes.py` 是两台已部署节点的可选验收用例。默认跳过；设置 `BUGGCRAFT_TEST_DEPLOYED=1` 和 `BUGGCRAFT_DEPLOYED_CONFIG` 后，会通过公网检查 HTTPS 页面与管理权限、UDP STUN、双向跨节点房间发现、路由、1 MiB 数据回传、EOF 和关闭清理，以及 SSH 公钥和错误凭据拒绝。它不停止服务器、不修改账号，测试房间会短暂显示在大厅，结束后关闭。

配置文件必须私下保存，不能提交到仓库。顶层 `nodes` 包含两项，每项为 `name`、`web_url`（不带末尾斜杠）、从可信服务器核对的 `tls_sha256`，以及完整 `profile`（`server_host/server_port/server_public_key/token`）。TLS 指纹和 SSH 公钥均固定校验，不接受关闭验证代替身份检查。公网 STUN 成功只说明 UDP 地址探测可达，不能代替不同客户端网络的 P2P 打洞验收。

`test_onboarding_browser.py` 使用真实浏览器完成桌面/窄屏操作、保存配置、后台登录和同页协议检查。安装 `requirements-test.txt` 并执行 `python -m playwright install chromium` 后，完整发现命令会包含此用例；未安装时明确跳过。也可用 `BUGGCRAFT_TEST_BROWSER` 指定浏览器路径，Windows 自动尝试已安装的 Edge。CI 的独立 browser 任务会安装 Chromium 后执行，不能因缺少浏览器跳过。

正式发布仍需核对证书提示、键盘操作，以及 systemd 安装、目录权限、服务器重启和升级后保留原身份。没有运行 systemd 的环境必须注明服务验收未执行，不能仅凭 unit 文件声称通过。

`test_systemd_service.py` 默认跳过，只有设置 `BUGGCRAFT_TEST_SYSTEMD=1` 才会操作系统服务，并拒绝使用已有节点数据。CI 独立 systemd 任务在一次性 Ubuntu 主机上以 root 执行它；不要在已有节点的服务器上开启。此用例验证重启服务，不等于实际重启整台服务器。
