# Buggcraft 联机节点

### 为朋友的世界，提供一个可信的连接入口。

Buggcraft 联机节点为启动器提供房间发现、联邦目录、好友与账号路由、P2P 信令，以及必要时的加密游戏流量中继。玩家可以自建节点；其他启动器也可以按公开协议接入。

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-6554c0.svg)](LICENSE)
[![Server tests](https://img.shields.io/github/actions/workflow/status/vdjango/minecraft-tunnel/server-tests.yml?label=tests)](https://github.com/vdjango/minecraft-tunnel/actions/workflows/server-tests.yml)
[![Issues](https://img.shields.io/github/issues/vdjango/minecraft-tunnel)](https://github.com/vdjango/minecraft-tunnel/issues)
[![Stars](https://img.shields.io/github/stars/vdjango/minecraft-tunnel?style=social)](https://github.com/vdjango/minecraft-tunnel)

**[部署节点](#部署节点)** · **[网页管理](#浏览器初始化)** · **[启动器接入](#启动器与-sdk-接入)** · **[报告问题](https://github.com/vdjango/minecraft-tunnel/issues)**

---

## 节点能做什么

| 房间与中继 | 联邦节点 | 账号与好友 |
|---|---|---|
| 发布大厅房间，处理邀请码和加入请求。 | 节点通过签名公告交换房间目录与存活状态。 | 账号密码保留在注册节点；可选择同步加密身份副本。 |
| 连接组件优先尝试 P2P；不可用时由房间归属节点中继。 | 不需要中心主节点；任意可信节点都可作为入口。 | 好友申请需要双方同意，用户名可跨联邦查询。 |
| 同一个房间允许 P2P 与中继连接并存。 | 管理员互换邀请后才建立信任关系。 | 匿名玩家可以联机，但没有好友功能。 |

节点负责发现、信令和中继。P2P 受双方 NAT、防火墙与 UDP 条件影响，并非所有网络都能打通。入口切换不能迁移已经建立的游戏 TCP 会话；房间归属节点失效时，玩家需要重新连接。联邦不合并带宽，也不替代外部 DDoS 防护。

## 部署节点

推荐下载包含运行环境的 [发行包](https://github.com/vdjango/minecraft-tunnel/releases)。无需安装 Python 或手工下载依赖；解压后保留完整目录。

开发包在 [GitHub Actions → Server regression](https://github.com/vdjango/minecraft-tunnel/actions/workflows/server-tests.yml)：选择绿色通过的构建，在 **Artifacts** 下载 `buggcraft-node-windows-x64-…` 或 `buggcraft-node-linux-x64-…`。Actions 产物保留 30 天，下载需要登录 GitHub；公开 Release 的下载不需要登录。

| 系统 | 运行方式 | 持久化数据 |
|---|---|---|
| Windows x64 | 双击 `buggcraft-node.exe`，首次自动打开浏览器向导。 | 程序旁的 `data/` |
| Linux x64（glibc） | 执行 `./buggcraft-node` 前台运行。 | 程序旁的 `data/` |
| Linux x64 + systemd | 执行 `sudo ./buggcraft-node --install-service` 安装开机启动服务。 | `/var/lib/buggcraft-node` |

Windows 包是前台应用，关闭控制台会停止节点；目前不注册 Windows 服务。支持目标为 Windows 10/11、Windows Server 2016+ x64；其他版本和不同 Linux 发行版需实际验证。发行包未签名时，Windows 可能阻止运行，当前签名及验收要求见[发布前检查](docs/release-readiness.md)。

首次设置都在浏览器完成，见[部署与维护说明](docs/deployment.md)。也可从源码安装 Linux systemd 服务，需要 Python 3.11+、`systemctl`、`useradd` 和与 Python 版本匹配的 venv 包：

```sh
git clone https://github.com/vdjango/minecraft-tunnel.git
cd minecraft-tunnel
sudo python3 src/main.py --install-service
```

安装器创建专用服务账户，启用 `buggcraft-node.service` 并设为开机启动。发行包安装直接复制内置运行环境；源码安装才创建 Python 环境并安装依赖。服务启动后，不需要再运行初始化脚本。

常用管理命令：

```sh
sudo systemctl status buggcraft-node
sudo systemctl restart buggcraft-node
sudo journalctl -u buggcraft-node -f
```

## 浏览器初始化

启动日志会显示一次性 HTTPS 链接和临时证书 SHA256 指纹。通过可信的服务器终端获取链接，核对指纹后在浏览器打开；不要转发含有 token 的链接。

三步向导设置节点地址与名称、管理员账号、房间容量及匿名接入策略。保存后，同一服务自动切换到正常节点页面。首次证书尚未被公开 CA 信任；面向公众提供服务前，请配置域名和可信 HTTPS 证书。

- **节点首页**：公开查看节点状态、房间和在线人数。
- **实时带宽**：查看服务器入口、出口速率，切换 MB/s 或 Mbps。
- **管理页面**：调整容量、开放方式、邮件服务和联邦关系。
- **启动器接入**：浏览器内直接阅读流程、语言示例与完整协议。

## 启动器与 SDK 接入

接入协议位于节点网页 `/developers`，也可以直接阅读[协议标准](PROTOCOL_STANDARD.md)。协议页面列出认证、房间、好友、账号路由、传输与错误处理，并提供 C/C++、Java、Python 和 C# 参考示例。接入方负责实现启动器侧连接组件；用户侧不需要填写打洞细节。

官方桌面端：[Buggcraft 启动器](https://github.com/vdjango/buggcraft)。它使用同一节点协议和连接组件，不要求部署节点的用户改动服务端代码。

## 端口与数据

默认放行 **TCP 18443**（网页）、**TCP 3333**（目录与游戏中继）和 **UDP 3333**（P2P 地址探测）。网页端口冲突时可在安装时设置 `--web-port 18444`；联机端口可在向导里设置。安装器不改已有网站或防火墙。

Linux 服务的程序发布在 `/opt/buggcraft-node`，节点数据在 `/var/lib/buggcraft-node`；前台发行包的数据保存在程序旁的 `data/`。更新服务时再次执行对应安装命令；安装器准备好新版本后再切换。备份和恢复说明见[部署文档](docs/deployment.md)。

## 开发与测试

`src/main.py` 是唯一应用入口；`src/tunnel/` 包含中继、联邦、向导和网页实现；`tests/` 为服务端 unittest。运行完整服务端套件：

```sh
python -X utf8 -m unittest discover -s tests -p "test_*.py" -v
```

测试覆盖真实 HTTPS 初始化、管理员和节点密钥、服务端口、SSH 中继、账号副本、联邦公告、STUN 与信令。systemd 安装验收由一次性 Linux CI 环境执行。跨公网 NAT 打洞、多个真实运营商网络及完整 Minecraft 负载仍需在对应网络环境验收；单元测试不会替代这些测试。详见[测试说明](tests/README.md)和[发布前检查](docs/release-readiness.md)。

## 许可与节点运营

源代码采用 [GNU AGPL v3](LICENSE) 发布。[社区贡献与资源赞助](COMMUNITY_LICENSE.md)说明参与方式，不增加许可限制。

自行部署节点并向公众提供中转服务，可能需要取得相应电信业务许可。节点部署者应根据所在地法律和实际服务方式，自行确认适用的许可、备案及数据保护等要求，并自行承担节点运营的合规责任。

## 参与和赞助

欢迎提交问题、修复代码、改进文档，或帮助验证不同系统和网络。

**不接受资金赞助，接受服务器、云主机、带宽、流量额度、对象存储及 CDN 等云上资源赞助。** 有意提供资源可先在 [Issues](https://github.com/vdjango/minecraft-tunnel/issues) 沟通用途和限制，请勿公开任何密码或密钥。详见[资源赞助政策](COMMUNITY_LICENSE.md#赞助政策)。

发行包构建和验收见[打包说明](docs/packaging.md)。

---

<p align="center"><sub>开源实现，节点由社区运行，是否加入由你决定。</sub></p>
