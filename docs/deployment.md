# 节点部署与维护

## 安装系统服务

使用 systemd 的 Linux，下载源码后在仓库目录执行：

```sh
sudo python3 src/main.py --install-service
```

前提是 Python 3.11+、对应的 venv 包、systemctl 和 useradd 可用。例如 Debian 12 / Ubuntu 24.04 可先通过系统包管理器安装 `python3` 和 `python3-venv`；旧系统需先准备符合版本要求的 Python。安装入口仅使用标准库，不要求提前安装应用依赖。

安装命令创建无登录权限的 `buggcraft-node` 用户、在 `/opt/buggcraft-node/releases` 准备独立代码和依赖环境，随后注册并启动 `buggcraft-node.service`，设置开机启动。应用入口仍是 `src/main.py`。只复制服务端源码、协议和依赖清单，不复制开发目录里的配置、测试和凭据。

首次启动会显示初始化链接，也可用 `sudo journalctl -u buggcraft-node -n 30 --no-pager` 获取链接和证书指纹。不要分享日志里的 token；初始化完成后链接失效，未完成时每次服务重启会更换 token。

默认网页为 HTTPS 18443，联机为 TCP/UDP 3333。需要同时放行云安全组和主机防火墙。初始化前只启动网页监听，保存配置后才启用联机端口。

服务以专用账户运行，systemd 限制系统目录写入，持久化数据位于 `/var/lib/buggcraft-node`，目录权限 0700。异常退出后等待 3 秒重启；主动停止不触发自动重启。日志进入 journald，由系统日志策略控制保留时间和磁盘占用。

```sh
sudo systemctl status buggcraft-node
sudo systemctl stop buggcraft-node
sudo systemctl start buggcraft-node
sudo systemctl restart buggcraft-node
sudo journalctl -u buggcraft-node -f
```

不需要手工编写 unit 文件，也不需要独立初始化脚本。已有同名但非本安装器管理的服务会被拒绝覆盖，必须先核对原服务的数据位置并安排迁移。

### 已有网站或多个节点

默认不占用 80/443，不修改网站或防火墙。若首次网页端口已被占用：

```sh
sudo python3 src/main.py --install-service --web-port 18444
```

在向导中设置可用的联机端口。专用服务账户使用 1024–65535 范围；需要对外使用 443 时应配置独立代理入口。初始化后监听端口以数据目录中的 `server.conf` 为准，安装参数不会覆盖已有配置。

默认安装器管理一个节点。额外节点可使用独立 systemd unit 调用同一 `main.py`，指定不同数据目录和首次网页端口；每个节点的联机端口也必须不同。不要让两个进程同时打开同一份数据。

## 浏览器向导

首次访问须持有启动日志中的随机 token。整个配置过程使用 TLS；无 token 请求不能读取表单或保存设置，跨站请求会被拒绝。首次证书未受公开 CA 信任，请在可信服务器控制台核对指纹。

向导保存名称、对外地址、管理员、容量及匿名接入策略，在服务内部生成 SSH 身份、联邦密钥和 HTTPS 证书。默认关闭玩家注册，节点独立运行。保存成功后自动切换正常网页。自选管理员密码仅保存为 scrypt 哈希，不写入日志或凭据说明文件。

后续管理仍在网页完成：

- **连接网络**：导入可信节点的联邦邀请，或导出邀请。没有邀请也可独立运行。
- **节点设置**：调整名称、开放策略、容量和带宽预算。单位 MB/s，Mbps 需除以 8。默认保留 35% 空闲，每位中转访客预算 0.128 MB/s，另计 15% 开销；预算不是峰值实测。
- **邮件服务**：配置 SMTP、确认验证码收件后，在“节点设置”开放注册。
- **节点列表**：查看成员状态。本地隔离及恢复需要目标确认、原因和管理员密码，不是全网踢除。

## 本地前台运行

开发或本地试用时可准备 Python 3.11+ 环境后前台启动。此方式不安装系统服务。Linux/macOS：

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

## HTTPS 与网络入口

节点证书在数据目录的 `web-cert.pem` 和 `web-key.pem`，配置项是 `server.conf` 的 `[web] tls_cert/tls_key`。替换为可信证书后重启，私钥只允许运行账户读取。自动生成的节点证书有效期一年，服务不会自动申请公开证书，到期前必须续签或替换。

可以配置 HTTPS 反向代理和独立 TCP 防护入口。代理到节点时保留 HTTPS，或通过安全的本机隧道访问；服务不信任任意 `X-Forwarded-*`。SSH 中转和 UDP STUN 需要单独转发，不能当作普通网页代理。源站是否隐藏取决于代理、DNS 和防火墙。没有防护入口时不能宣称能抵御容量型 DDoS。

独立 TCP 入口在向导可选字段中设置。玩家接入码须包含可达的入口地址和匹配的 SSH 公钥，不能把监听地址误当公开入口，也不能随意替换 SSH 身份。

## 数据、备份与升级

节点私钥、联邦密钥、管理员哈希、SMTP 配置和账号副本须私下保存。`admin-credentials.txt` 包含随机生成的玩家接入密码和证书指纹；自选管理员密码不明文写入。普通玩家领取个人接入码，不要向玩家发送原始 profile、联邦邀请或整个配置目录。

执行 `sudo systemctl stop buggcraft-node` 后备份完整 `/var/lib/buggcraft-node`，并保护备份权限；仅备份 `server.conf` 无法恢复身份。确认可恢复后再升级。重启会断开游戏连接，应安排维护时间。

更新源码后再次运行 `sudo python3 src/main.py --install-service`。先在新的 release 目录准备依赖，成功后停止旧进程、切换 `current` 并启动；准备失败不会停止旧服务。切换或启动命令失败会恢复原链接和 unit，原先运行的服务会尝试重新启动。安装器不修改节点数据，也不负责回滚数据格式变更。切换后的运行期故障仍需查看日志处理，不能将进程已启动当作完整健康验收。

旧 release 保留在 `/opt/buggcraft-node/releases`，失败的准备目录也保留便于排查，不自动清理。恢复时保留原 SSH 私钥、联邦密钥和账号数据，不能同时运行原节点与克隆。卸载服务可执行 `sudo systemctl disable --now buggcraft-node` 后移除 unit 并 `daemon-reload`；保留数据目录以备恢复。

## 故障排查

- 页面无法访问：确认 `systemctl status` 正常、监听端口正确、云安全组与主机防火墙已放行网页 TCP 端口。
- 初始化链接失效：确认是否已初始化；未完成时使用当前日志的新链接。
- 保存失败：检查目录权限、可用磁盘及输入。写盘失败会清理本次创建的配置，可以修正后重试。
- 保存后节点退出：检查监听冲突、配置或证书错误；修正后重启，不要删除密钥重新初始化。
- 网页可用但不能联机：检查联机 TCP、公开入口和 SSH 公钥；地址探测还需要 UDP，UDP 不通时客户端应回退中转。

覆盖范围见 [测试说明](../tests/README.md)，发布要求见 [发布前检查](release-readiness.md)。
