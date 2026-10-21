# Buggcraft 联机节点

`minecraft-tunnel` 是 Buggcraft 的自建联机节点服务端。它提供房间目录、节点间无主联邦、P2P 信令和加密 SSH 中转；启动器通过连接组件使用这些能力，不需要自己实现打洞或中继协议。

服务端需要 Python 3.11+、AsyncSSH、`aiohttp` 和 `cryptography`。不需要 Docker、虚拟网卡或驱动。

## 先运行一个节点

在仓库根目录执行。Windows 使用 `.venv\Scripts\python.exe`，Linux/macOS 使用 `.venv/bin/python`。

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe deploy\init_node.py --directory config\my-node --public-host YOUR_HOST --port 3334 --web-port 18443 --name "我的社区节点"
.venv\Scripts\python.exe src\main.py --config config\my-node\server.conf
```

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python deploy/init_node.py --directory config/my-node --public-host YOUR_HOST --port 3334 --web-port 18443 --name "我的社区节点"
.venv/bin/python src/main.py --config config/my-node/server.conf
```

开放 TCP `3334`（联机中转）和 TCP `18443`（节点网页）；需要 P2P 地址探测时同时开放 UDP `3334`。端口可在初始化参数和生成的 `server.conf` 中修改。初始化目录包含密钥、管理员密码、玩家接入密码和自签名证书，已被 `.gitignore` 排除，必须私下保管。

节点网页公开展示名称、健康状态、房间和在线人数，不展示源站监听地址。自签名证书只适合测试；正式使用请配置自己的域名和可信证书。网页脱敏不能隐藏网络层地址，真正的源站保护仍需要独立 TCP 防护/代理入口。

### 部署者责任提示

自行部署节点并向公众提供中转服务，可能需要取得相应电信业务许可。节点部署者应根据所在地法律和实际服务方式，自行确认适用的许可、备案及数据保护等要求，并自行承担节点运营的合规责任。使用本项目不代表已取得相关许可，项目提供方不代替部署者办理或判断上述事项。

## 节点联邦

每个节点都是平等成员，没有必须在线的主节点，也没有远程“踢出全网节点”的命令。成员使用签名公告和共享入网密钥互相验证，约每 2 秒同步，公告约 10 秒过期。任一节点不可用时，启动器可以使用缓存的其他入口；已经建立的游戏 TCP 连接不能无缝迁移，玩家需要重连。

联邦最多 32 个互相信任的运营节点。管理员在网页 `/admin` 导出邀请，另一节点导入后逐步发现成员；联邦邀请只给可信运营者，不能发给普通玩家。节点本地可以隔离可疑成员，但这只影响本节点，不是全网封禁。

房间由创建它的节点负责中转。每位访客独立选择 `auto`（先 P2P，失败后中继）或 `relay`（只中继），同一个房间可以混合两种路径。P2P 会让通信双方获得网络候选地址；重视隐私时使用只中继。STUN 只做地址发现，不是 TURN 中继，NAT 或防火墙可能导致只能中继。

账号密码不会进入联邦目录。联邦同步公开用户名、签名路由、签名好友事件和用户授权的加密身份副本；密码在客户端用于解锁加密身份包，不发送给节点。额外副本数量由用户选择；全部身份副本不可用且没有恢复文件时无法重新登录。匿名接入码可以联机，但没有好友和账号能力。

## 目录和代码

```text
src/main.py                 唯一正式服务入口
src/tunnel/                 中继、目录、联邦、账号、网页和 P2P 信令
deploy/init_node.py         生成密钥、证书和节点配置
deploy/buggcraft-relay.service  systemd 服务模板
deploy/local_cluster.py     本机启动四个隔离节点，供集成验收
deploy/check_*.py           已启动节点的验收编排，不是测试套件
tests/                      服务端 unittest 测试，直接断言实际行为
```

`requirements.txt` 统一维护服务端依赖。启动器和 P2P 客户端组件的依赖由启动器仓库维护，节点本身不需要安装 Qt 或 aiortc。

## 测试和验收

安装依赖后运行服务端测试套件：

```sh
python -X utf8 -m unittest discover -s tests -p "test_*.py" -v
```

测试使用临时配置和本机真实 SSH/HTTP 服务，覆盖容量准入、流量统计、联邦心跳、账号副本补位、网页权限、邮件验证码、P2P 信令权限和 STUN 协议。覆盖范围及跨仓库 P2P 测试方法见 [测试说明](tests/README.md)。

需要启动器仓库才能运行跨仓库集成测试：

```sh
python deploy/check_server.py
```

没有相邻 `buggcraft` 时使用 `--native-only`，只运行本仓库测试。`deploy/local_cluster.py`、`deploy/check_cluster.py`、`deploy/check_accounts_web.py`、`deploy/check_capacity_web.py` 和 `deploy/check_console_web.py` 会启动真实节点或浏览器，适合发布前验收；它们不会替代 `tests/`。

## 生产运行

`deploy/buggcraft-relay.service` 是 systemd 模板，不是自动部署器。复制前修改绝对路径、服务账户、配置目录和端口，使用独立的 `buggcraft-node` 账户运行；不要把 `config/my-node` 复制进 Git。升级会中断已有连接，应提前备份密钥并安排维护窗口。

完整端口、联邦、账号副本、容量和开放接口说明见 [部署说明](deploy/README.md) 和 [协议标准](PROTOCOL_STANDARD.md)。网页中的第三方启动器接入文档位于 `/developers`。

- [测试覆盖与 P2P 验证边界](tests/README.md)
- [发布前检查](docs/release-readiness.md)
- [LICENSE](LICENSE) 与 [社区许可说明](COMMUNITY_LICENSE.md)
