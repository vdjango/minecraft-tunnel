# Buggcraft 联机节点

自建联机节点服务端，提供房间目录、无主联邦、账号与好友路由、P2P 信令和加密 SSH 中转。启动器通过连接组件接入，不需要自己实现打洞。

## 部署：启动服务，其余在浏览器完成

下载本仓库后，在仓库目录执行。适用于使用 systemd 的 Linux，需准备 Python 3.11+ 和对应的 venv 包：

```sh
sudo python3 src/main.py --install-service
```

这条命令创建独立依赖环境、专用服务账户和 `buggcraft-node.service`，启动服务并设置开机启动。终端会显示首次初始化链接；也可查看服务日志：

```sh
sudo journalctl -u buggcraft-node -n 30 --no-pager
```

打开日志中的 `https://服务器地址:18443/?token=…`，把 `SERVER_IP` 换成服务器实际地址。链接只能由部署者保管。浏览器向导会依次设置：

1. 节点名称、域名或公网地址，已有 TCP 防护入口也在这里填写。
2. 管理员用户名和密码。
3. 房间数、每房间人数、上传带宽预算，以及是否允许匿名接入。

保存后自动开始提供服务，无需再执行初始化命令或重启。之后访问 `https://服务器地址:18443/` 查看公开状态，`/admin` 管理节点。网页的“启动器接入”入口提供同一页面内的流程、各语言示例和完整协议。

首次使用自签名证书，浏览器会提示证书未受信任。初始化证书 SHA256 指纹会与链接一起写到启动日志，请通过可信服务器控制台核对；配置完成后节点会使用独立的长期证书。公开使用前应配置域名和可信证书，见 [部署说明](docs/deployment.md)。

放行 **TCP 18443**（网页）、**TCP 3333**（联机/中转）及 **UDP 3333**（P2P 地址探测）。不修改已有网站、反向代理和防火墙。联机端口可在向导中修改；首次网页端口冲突时，安装命令增加 `--web-port 18444`。

代码和依赖在 `/opt/buggcraft-node`，节点数据在 `/var/lib/buggcraft-node`。日常管理：

```sh
sudo systemctl status buggcraft-node
sudo systemctl restart buggcraft-node
sudo systemctl stop buggcraft-node
sudo systemctl start buggcraft-node
```

更新源码后再次执行安装命令，保留节点数据。安装细节、备份和更新失败恢复见 [部署说明](docs/deployment.md)。

### 本地前台运行

安装 Python 3.11+ 和 `requirements.txt` 的依赖后，只需一条启动命令：

```sh
python src/main.py
```

首次同样进入 HTTPS 向导，默认数据目录 `config/node`。后续使用同一命令即可。可通过 `--directory config/another-node --web-port 18444` 启动另一节点；显式 `--config PATH` 只运行已有配置，不会初始化。唯一应用入口是 `src/main.py`，安装和初始化都由此进入。

## 联邦与连接方式

节点平等，不依赖主节点。成员使用签名公告和共享入网密钥互相验证，约每 2 秒同步，公告约 10 秒过期。联邦最多 32 个互信运营节点。管理员在网页“连接网络”导出或导入邀请；邀请仅给可信运营者，不能发给玩家。隔离可疑成员仅影响本节点，没有任意成员可以调用的全网踢除接口。

玩家可以从任意联邦入口查找房间，房间由创建它的节点负责中转。每位访客独立选择先 P2P、失败后中继的 `auto`，或仅中继的 `relay`，同房间可以混合。P2P 会向对端提供网络候选地址。STUN 仅做地址发现，不能保证穿透所有 NAT。

入口故障时可以使用备用节点，但现有 TCP 和游戏会话不能迁移；归属节点失效需要重新建房和加入。联邦不聚合带宽，也不能替代 DDoS 防护。网页不展示监听地址，不等于网络层隐藏源站。

账号密码不进入联邦目录；公开用户名、签名路由和好友事件在网络中传播，用户可选择加密身份副本数量。密码在客户端解锁身份包。全部副本和恢复文件均丢失时无法重新登录。匿名接入可联机，没有好友功能。

## 代码和测试

|位置|职责|
|---|---|
|`src/main.py`|唯一应用入口，首次向导与正常运行|
|`src/tunnel/onboarding.py`、`provisioning.py`|服务内部的首次配置与密钥生成|
|`src/tunnel/`|中转、联邦、账号、网页与 P2P 信令|
|`src/tunnel/service.py`|systemd 服务安装、独立依赖环境和更新回滚|
|`tests/`|断言实际行为的 unittest 用例，无需预先部署节点|

```sh
python -X utf8 -m unittest discover -s tests -p "test_*.py" -v
```

用例覆盖真实 HTTPS 初始化与服务切换、SSH 传输、容量、联邦心跳、账号副本、权限、邮件、STUN 和 P2P 信令。完整客户端 ICE 测试在启动器仓库；本机直连不代表跨公网 NAT 验收，见 [测试说明](tests/README.md) 和 [发布前检查](docs/release-readiness.md)。

### 部署者责任提示

自行部署节点并向公众提供中转服务，可能需要取得相应电信业务许可。节点部署者应根据所在地法律和实际服务方式，自行确认适用的许可、备案及数据保护等要求，并自行承担节点运营的合规责任。使用本项目不代表已取得相关许可，项目提供方不代替部署者办理或判断上述事项。

- [部署与维护](docs/deployment.md)
- [协议标准](PROTOCOL_STANDARD.md)
- [LICENSE](LICENSE) 与 [社区许可说明](COMMUNITY_LICENSE.md)
