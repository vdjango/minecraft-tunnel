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
|`test_relay_security.py`|错误 token/角色/房间密钥、公钥不匹配、禁止 shell/exec/SFTP、目录越权、任意转发、超长帧、失效凭据|
|`test_capacity.py`|人数计数、并发准入、跨房间预算、容量调整、游戏人数与过期、真实双向转发字节|
|`test_heartbeat.py`|多节点发现、SSH 配置隔离、部分节点失败后继续同步|
|`test_federation_integrity.py`|签名/网络证明篡改、心跳重放、过期/未来公告、大小限制、房间归属冲突、本地隔离范围|
|`test_account_replication.py`|四节点实际 SSH 同步、目录与密文分离、副本数、非副本路由、故障补位、撤回副本、策略篡改、重名及重启恢复|
|`test_portal_governance.py`|公开/受保护页面、CSRF、再次鉴权、本地隔离/恢复/审计、后台路由、SMTP 脱敏、同页协议和接入示例、错误公钥|
|`test_mail.py`|验证码绑定/消费/过期/重放/限速、HTML 转义、敏感数据不进入邮件或错误、STARTTLS 后认证|
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

`test_onboarding_browser.py` 使用真实浏览器完成桌面/窄屏操作、保存配置、后台登录和同页协议检查。安装 `requirements-test.txt` 并执行 `python -m playwright install chromium` 后，完整发现命令会包含此用例；未安装时明确跳过。也可用 `BUGGCRAFT_TEST_BROWSER` 指定浏览器路径，Windows 自动尝试已安装的 Edge。CI 的独立 browser 任务会安装 Chromium 后执行，不能因缺少浏览器跳过。

正式发布仍需核对证书提示、键盘操作，以及容器构建、卷权限、服务器重启和升级后保留原身份。没有 Docker 引擎的环境必须注明未执行，不能仅凭配置文件声称通过。
