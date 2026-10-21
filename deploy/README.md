# 部署与维护联邦节点

本目录保留节点初始化、Linux 常驻服务和本地集群工具。服务运行入口统一为 `src/main.py`，依赖统一为根目录 `requirements.txt`。所有命令从 `minecraft-tunnel` 仓库根目录执行。

向公众提供中转服务前，请先阅读 [README 中的部署者责任提示](../README.md#部署者责任提示)，自行确认适用的许可、备案和运营要求。

## 1. 初始化并启动

需要 Python 3.11+。Windows PowerShell：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe deploy\init_node.py --directory config\my-node --public-host YOUR_HOST --port 3334 --web-port 18443 --name "我的社区节点"
.venv\Scripts\python.exe src\main.py --config config\my-node\server.conf
```

Linux/macOS：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python deploy/init_node.py --directory config/my-node --public-host YOUR_HOST --port 3334 --web-port 18443 --name "我的社区节点"
.venv/bin/python src/main.py --config config/my-node/server.conf
```

将 `YOUR_HOST` 换为玩家可以访问的域名或地址，不带 `https://`、路径或端口。示例使用 3334，初始化器未指定 `--port` 时默认 3333。不要直接运行模板 `config/server.conf`：它没有密钥、网页和联邦状态；应使用初始化器生成的配置。

初始化拒绝覆盖已有配置和密钥。再次启动只运行最后一条命令；不要重新初始化。服务日志写到标准错误，systemd 会交给 journal 保存。

|端口（示例）|用途|是否需要|
|---|---|---|
|TCP 3334|SSH 控制、联邦同步、P2P 信令和游戏中转|需要|
|UDP 3334|STUN 地址发现，与 SSH 使用同一个端口号|建议开放；不可用时仍能中转|
|TCP 18443|节点 HTTPS 网页和管理接口|网页需要|

同时检查主机防火墙、云安全组及路由器映射。节点不需要占用已有网站的 80/443，不需要向公网开放房主的游戏端口。STUN 不是 TURN；仅开放节点 UDP 不能保证所有 NAT 环境都能直连。

## 2. 配置文件和证书

`config/my-node/` 是整个节点的持久数据目录。以下文件都不能公开或提交 Git：

|文件|用途|
|---|---|
|`server.conf`|监听端口、资源上限、网页证书路径|
|`relay_host_key`、`relay.token`|SSH 身份和匿名接入凭据|
|`relay-profile.json`|含入口、固定 SSH 公钥和玩家凭据的导入资料|
|`node-state.json`|管理密码摘要、联邦密钥、成员和本地规则|
|`admin-credentials.txt`|初始管理员密码、玩家访问密码、网页证书 SHA-256|
|`web-key.pem`、`web-cert.pem`|网页私钥和自签名证书|
|`accounts-*.json`、`friends-signed.json`|运行后产生的账号路由、加密副本和签名好友事件|
|`smtp.json`|发信配置，包含明文 SMTP 授权码|

限制 Linux 文件权限或 Windows ACL。备份整个数据目录时同样限制访问，升级时保留原密钥，否则客户端固定公钥校验会拒绝连接。

默认证书为自签名，首次测试通过可信渠道核对 `admin-credentials.txt` 中的 SHA-256。公开运行建议使用域名和可信 CA 证书，在 `[web]` 配置 `tls_cert`、`tls_key` 后重启。配置内相对路径均相对 `server.conf` 所在目录解析。非本机明文 HTTP 不允许授权；SSH 公钥校验与网页证书校验是两套独立的保护。

通过 TCP 防护代理接入时，初始化可传 `--entry-host proxy.example --entry-port 443`，生成对外入口资料。已有配置可在 `[relay]` 设置 `entry_host`、`entry_port`；它们只改变公告地址，不会自动创建代理或配置防火墙。网页另行配置 HTTPS 代理和证书，源站限制到可信入口。接入码编码与页面不显示 IP 都不能隐藏真实连接地址。

## 3. 玩家接入与账号

访问 `https://YOUR_HOST:18443/` 查看公开状态、领取接入码。管理员入口为 `/admin`，与玩家账号登录分开。

普通接入码用于匿名联机。玩家输入访问密码领取，或由管理员允许公开领取；在启动器大厅的节点菜单导入。导入时固定验证 SSH 公钥，再测试连接。匿名玩家可以跨联邦找房和使用备用入口，没有好友功能。

需要账号身份时，玩家在网页注册/登录后领取个人接入码，再导入同一个启动器入口。个人码含账号授权，最长七天有效，可用于自己的其他设备，不能发给朋友。网页登录退出不会撤销已发出的码。关闭普通码领取或修改玩家访问密码，也不会撤销已领取的普通码；需要停服轮换 `relay.token`、更新资料并重新发码。

注册默认关闭；管理员在账号设置中开启。用户名为 3–32 位 ASCII 字母、数字、下划线或连字符，不区分大小写查重。注册默认要求邮箱验证码，未配置 SMTP 时拒绝完成注册；管理员可以明确关闭邮箱验证要求。

密码在浏览器解锁加密身份并完成签名，不发到节点，不保存在浏览器作为后续登录依据。换设备可以输入密码解锁服务端返回的加密身份包。用户名、账号 ID、公钥和签名路由默认同步到联邦，不依赖用户是否备份；加密身份包由用户选择 0–8 个额外持久副本。非副本节点可路由到在线注册节点或副本，临时获取密文并验证签名。在线副本不足时会尝试补位；全部副本和恢复文件都丢失时无法恢复身份。

个人接入码支持按用户名或完整账号 ID 查找好友、申请、同意、在线状态和房间邀请。好友关系为双方签名事件，经联邦传播；不等于任何一方可以绕过房间邀请。没有加密身份副本也能验证已签发的个人授权和签名好友事件，但不能凭空恢复已经丢失的身份包。网络分区可能造成重名，应使用完整 ID 区分。

加密不能防止弱密码被离线猜测，也不能防止恶意节点网页窃取输入。仅在信任的节点网页使用独立长密码，保管恢复文件；减少副本数量不能收回运营者的历史拷贝。

## 4. 组成联邦

A 管理员导出邀请，B 管理员在自己的后台导入；C、D 可以导入 A 或 B 的邀请。成员会传递发现，无需逐对添加。邀请含入网密钥，只交给互相信任的运营者。最多 32 个成员，不支持直接合并两个已运行的联邦；已有联邦或活动房间时，切换网络会被拒绝。

每个成员签名自己的目录，无主节点和选举。同步周期约两秒，目录有效期十秒；重放旧公告不能续期。健康状态区分直接在线、间接可见、可疑、离线与本地隔离。

在 A 创建的房间由 A 承担中转，B 提供目录和归属定位，客户端验证 A 公钥后连接 A。P2P 成功时游戏数据直接在房主与访客间传输；每位访客分别协商，可与只中转的访客共处一室。私密房间只传播随机房间 ID，不传播名称和加入密钥；世界存档留在房主电脑。

后台隔离成员需要本机管理员会话、CSRF、完整目标 ID、原因和再次验证管理员密码。操作只改变本机规则，不能踢掉全网成员；本地记录最多 100 条。共享入网密钥泄露后，恶意运营者可能更换节点身份，需可信成员协调更换网络密钥和凭据。

启动器成功发现网络后缓存备用入口。入口失效可尝试其他成员，但首次使用且没有缓存的客户端仍需要一个可达入口。中转节点失效会断开现有游戏 TCP；房主可在备用节点重建，访客重新定位并重进游戏。多节点不会聚合带宽，也不能独立抵御容量型 DDoS。

## 5. 人数、容量与带宽

公开页展示房间数、房间成员和游戏内人数。成员包括房主和启动器访客，不包括心跳、目录或转发通道。游戏人数由房主读取游戏状态后上报，过期或读取失败显示未知，不将未知当成零。

管理员可设置最大房间数、每房间成员数、出口带宽、预留比例和单人预算。统一使用十进制 MB/s：`1 MB/s = 1,000,000 字节/秒`。无论家庭宽带还是云服务器，若标注 Mbps 就除以 8；不要把 Mbps 当成 MB/s，应使用可用上传/出网带宽。

全节点访客预算为 `floor(出口 MB/s × (1 − 预留比例) / (单人 MB/s × 1.15))`。默认单人预算 0.128 MB/s、预留 35%，再计 15% 协议开销，1 MB/s 的预算得到四位访客。它是可调的准入预算，未经真实游戏峰值标定，不是固定游戏耗量或流畅承诺。首次进服、区块、视距、模组和其他业务都影响带宽。

带宽填 0 关闭带宽准入，房间容量限制仍生效。降低上限不会踢出现有玩家。此规则控制准入，不是带宽整形，P2P 访客的成员连接也参与准入。页面速率是约十秒的双向游戏中转有效负载均值，不含 SSH/网络包头和 P2P 数据，不等于网卡出网账单。

SDK 延迟来自沿游戏路径的 Minecraft 列表 Ping/Pong，排除握手；没有 Pong 时显示未知，与游戏内 TAB 的 KeepAlive 统计可能不同。

## 6. Linux 常驻与升级

[buggcraft-relay.service](buggcraft-relay.service) 假定代码位于 `/opt/buggcraft-node`，服务账户为 `buggcraft-node`，配置为 `config/node/server.conf`。管理员应先创建专用账户，把代码设为只读、配置目录交给服务账户，并以该账户初始化 `config/node`。再按实际路径修改模板，安装服务：

```sh
sudo install -m 644 deploy/buggcraft-relay.service /etc/systemd/system/buggcraft-relay.service
sudo systemctl daemon-reload
sudo systemctl enable --now buggcraft-relay
sudo systemctl status buggcraft-relay
sudo journalctl -u buggcraft-relay -n 100 --no-pager
```

模板只允许写 `config/node`，改数据目录时同时改 `ReadWritePaths`；证书私钥也必须可被服务账户读取。已有网站的机器使用新目录、空闲端口和独立服务名。

升级前备份配置与密钥，记录当前提交，停止服务、更新代码和 `requirements.txt` 依赖、运行回归，再启动并检查网页和真实房间。升级会断开连接，应安排维护时间；回滚使用原代码和兼容的数据备份，不要重新生成身份。

## 7. 测试、工具与开发者文档

测试用例位于 `tests/`，标准运行命令与覆盖清单见 [测试说明](../tests/README.md)。CI 直接运行 unittest，不以脚本打印 PASS 代替用例。

`deploy/local_cluster.py` 用于本机四进程联邦：SSH 34331–34334、HTTPS 18443–18446，只绑定回环地址；默认凭据目录 `config/local-cluster/[A-D]/`。Ctrl+C 停止，或指定 `--seconds 60` 自动停止。参数改变时使用新的配置目录，避免复用旧端口配置。

`deploy/check_*.py` 是已有本地环境的可选验收工具。它们的依赖、修改范围和命令统一放在 [测试说明](../tests/README.md)，不用于线上节点巡检。

第三方启动器从网页 `/developers` 接入，协议下载为 `/protocol.md`。推荐使用连接组件的 JSON-RPC 2.0 stdio API，由组件处理固定公钥、P2P 和中转。当前参考组件在独立的 [buggcraft 仓库](https://github.com/vdjango/buggcraft)，节点仓库不含客户端发行包；完整接口见 [协议标准](../PROTOCOL_STANDARD.md)。
