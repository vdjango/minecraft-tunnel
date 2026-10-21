# 节点部署与维护

## 容器服务

在仓库根目录运行 `docker compose up -d --build`。Docker 完成构建后在后台运行节点，首次等待浏览器初始化。用 `docker compose logs node` 获取一次性链接和初始化证书指纹。不要分享日志里的 token；初始化完成后链接失效，未完成时每次服务重启会更换 token。

默认网页为 HTTPS 18443，联机为 TCP/UDP 3333。需要同时放行云安全组和主机防火墙。初始化前只启动网页监听，保存配置后才启用联机端口。

容器以非 root 用户运行，应用文件只读，只有数据卷和临时目录可写。`restart: unless-stopped` 负责进程异常退出及服务器重启后的恢复；人为停止的服务不会自动恢复。日志每份最多 10 MB，保留 3 份。用 `docker compose ps` 查看容器，用 `docker compose logs --tail 100 node` 查看近期日志。

### 已有网站或多个节点

默认不占用 80/443。若 18443 或 3333 已被占用，启动前修改 `compose.yaml` 的映射左侧，例如：

```yaml
ports:
  - "3334:3333/tcp"
  - "3334:3333/udp"
  - "18444:18443/tcp"
```

此时初始化地址是 `https://服务器地址:18444/`，日志中的内部 18443 需换成外部端口。向导监听端口保持 3333/18443；展开“已有独立 TCP 代理入口”，将对外联机域名设为服务器地址、对外端口设为 3334。完成页面给出的后台链接也需换成外部 18444。默认部署无需这一步。

多个节点使用不同 Compose 项目名及不冲突的端口，每个项目保留独立数据卷。不要让两个进程同时打开同一份数据。

## 浏览器向导

首次访问须持有启动日志中的随机 token。整个配置过程使用 TLS；无 token 请求不能读取表单或保存设置，跨站请求会被拒绝。首次证书未受公开 CA 信任，请在可信服务器控制台核对指纹。

向导保存名称、对外地址、管理员、容量及匿名接入策略，在服务内部生成 SSH 身份、联邦密钥和 HTTPS 证书。默认关闭玩家注册，节点独立运行。保存成功后自动切换正常网页。自选管理员密码仅保存为 scrypt 哈希，不写入日志或凭据说明文件。

后续管理仍在网页完成：

- **连接网络**：导入可信节点的联邦邀请，或导出邀请。没有邀请也可独立运行。
- **节点设置**：调整名称、开放策略、容量和带宽预算。单位 MB/s，Mbps 需除以 8。默认保留 35% 空闲，每位中转访客预算 0.128 MB/s，另计 15% 开销；预算不是峰值实测。
- **邮件服务**：配置 SMTP、确认验证码收件后，在“节点设置”开放注册。
- **节点列表**：查看成员状态。本地隔离及恢复需要目标确认、原因和管理员密码，不是全网踢除。

## 原生 Python 运行

选择原生安装时需要先准备 Python 3.11+ 环境。Linux/macOS：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python src/main.py
```

Windows：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe src\main.py
```

首次从日志链接进入浏览器；以后仍执行最后一条命令。默认数据目录 `config/node`。`--directory PATH` 修改数据目录，`--web-port PORT` 修改首次 HTTPS 端口；初始化后端口由 `server.conf` 决定。显式 `--config PATH` 仅运行已有配置，文件缺失会报错。

### systemd 后台服务

不使用容器的 Linux 可由 systemd 管理同一个入口。以下假设代码和 venv 在 `/opt/buggcraft-node`，数据在 `/var/lib/buggcraft-node`，已创建无登录权限的 `buggcraft-node` 用户并赋予数据目录写权限。保存到 `/etc/systemd/system/buggcraft-node.service`：

```ini
[Unit]
Description=Buggcraft federation node
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=buggcraft-node
Group=buggcraft-node
WorkingDirectory=/opt/buggcraft-node
ExecStart=/opt/buggcraft-node/.venv/bin/python -u /opt/buggcraft-node/src/main.py --directory /var/lib/buggcraft-node
Restart=on-failure
RestartSec=3
TimeoutStopSec=20
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/buggcraft-node
UMask=0077
LimitNOFILE=8192

[Install]
WantedBy=multi-user.target
```

执行 `sudo systemctl daemon-reload`、`sudo systemctl enable --now buggcraft-node`。链接在 `sudo journalctl -u buggcraft-node -n 30` 中。容器和 systemd 二选一，不能对同一目录同时启动。

## HTTPS 与网络入口

节点证书在数据目录的 `web-cert.pem` 和 `web-key.pem`，配置项是 `server.conf` 的 `[web] tls_cert/tls_key`。替换为可信证书后重启，私钥只允许运行账户读取。自动生成的节点证书有效期一年，服务不会自动申请公开证书，到期前必须续签或替换。

可以配置 HTTPS 反向代理和独立 TCP 防护入口。代理到节点时保留 HTTPS，或通过安全的本机隧道访问；服务不信任任意 `X-Forwarded-*`。SSH 中转和 UDP STUN 需要单独转发，不能当作普通网页代理。源站是否隐藏取决于代理、DNS 和防火墙。没有防护入口时不能宣称能抵御容量型 DDoS。

独立 TCP 入口在向导可选字段中设置。玩家接入码须包含可达的入口地址和匹配的 SSH 公钥，不能把监听地址误当公开入口，也不能随意替换 SSH 身份。

## 数据、备份与升级

节点私钥、联邦密钥、管理员哈希、SMTP 配置和账号副本须私下保存。`admin-credentials.txt` 包含随机生成的玩家接入密码和证书指纹；自选管理员密码不明文写入。普通玩家领取个人接入码，不要向玩家发送原始 profile、联邦邀请或整个配置目录。

停止节点后备份完整数据目录或 Docker 数据卷，并保护备份权限；仅备份 `server.conf` 无法恢复身份。确认可恢复后再升级。重启会断开游戏连接，应安排维护时间。

容器更新源码后再次运行 `docker compose up -d --build`。停止用 `docker compose stop`，恢复用 `docker compose start`。`docker compose down` 保留卷，**加 `-v` 会删除数据**。恢复时保留原 SSH 私钥、联邦密钥和账号数据，不能同时运行原节点与克隆。

## 故障排查

- 页面无法访问：确认服务运行、映射正确、云安全组与主机防火墙已放行网页 TCP 端口。
- 初始化链接失效：确认是否已初始化；未完成时使用当前日志的新链接。
- 保存失败：检查目录权限、可用磁盘及输入。写盘失败会清理本次创建的配置，可以修正后重试。
- 保存后节点退出：检查监听冲突、配置或证书错误；修正后重启，不要删除密钥重新初始化。
- 网页可用但不能联机：检查联机 TCP、公开入口和 SSH 公钥；地址探测还需要 UDP，UDP 不通时客户端应回退中转。

覆盖范围见 [测试说明](../tests/README.md)，发布要求见 [发布前检查](release-readiness.md)。
