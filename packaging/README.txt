Buggcraft Node / 联机节点
========================

Windows 10/11 x64、Windows Server 2016+ x64：
  解压整个压缩包，双击 buggcraft-node.exe。首次运行自动打开本机浏览器向导。
  保留 _internal 文件夹。无需安装 Python、pip 或下载运行依赖。
  控制台中的 SERVER_IP 替换为服务器地址，可从其他电脑打开初始化链接。
  关闭控制台会停止节点。Windows 包目前以前台应用运行，不注册 Windows 服务。

Linux x64（glibc）：
  前台运行：./buggcraft-node
  安装开机启动服务：sudo ./buggcraft-node --install-service
  查看初始化链接：sudo journalctl -u buggcraft-node -n 30 --no-pager
  管理服务：sudo systemctl status/restart/stop buggcraft-node
  发行包需要在目标系统上验收，不支持 Alpine/musl。

数据与日志：
  前台运行默认保存在程序旁 data/，日志 data/logs/node.log（滚动保留）。
  Linux 安装服务后保存在 /var/lib/buggcraft-node，日志也进入 journal。
  默认 HTTPS 18443、联机 TCP/UDP 3333；请按需放行云安全组和防火墙。
  首次证书为自签名，请核对控制台 SHA256 指纹；初始化链接含秘密，不要分享。
  对外提供服务前配置可信 HTTPS 证书。不要公开 data/、接入码或日志里的秘密。
  升级前停止旧节点并备份 data/；在新解压目录放回原 data/，不要覆盖私钥重新初始化。
  未签名发行包可能被 Windows 拦截；不要关闭系统防护。签名状态见 build-info.json。

协议与源码：
  节点首页 /developers 可直接阅读接入流程、语言实例及完整协议。
  SOURCE.tar.gz 为本次构建源码；LICENSE 为 AGPL v3，licenses/ 为依赖许可。
  构建记录：build-info.json。压缩包 SHA256 文件仅用于核对完整性，不能代替代码签名。
  文档：https://github.com/vdjango/minecraft-tunnel/blob/main/docs/deployment.md
  问题反馈：https://github.com/vdjango/minecraft-tunnel/issues

本项目不接受资金赞助，接受服务器、云主机、带宽等云资源赞助。
