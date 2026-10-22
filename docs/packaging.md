# 发行包与验收

发行包按目标系统分别构建，不能在 Windows 构建 Linux，也不能在 Linux 构建 Windows。当前发布目标是 Windows x64 和使用 glibc 的 Linux x64；构建机必须与目标系统匹配。包使用 PyInstaller，运行时和 Python 依赖放在包内，用户不需要安装 Python、pip 或在首次启动时联网下载依赖。

## 构建

在干净的 Python 3.11 x64 环境中执行：

```powershell
python -m venv .build-env
.build-env\Scripts\python.exe -m pip install -r requirements-build.txt
.build-env\Scripts\python.exe build.py
```

Linux 使用：

```sh
python3 -m venv .build-env
.build-env/bin/python -m pip install -r requirements-build.txt
.build-env/bin/python build.py
```

构建结果在 `dist/buggcraft-node-windows-x64.zip` 或 `dist/buggcraft-node-linux-x64.tar.gz`，旁边有 `.sha256` 校验文件。包中包括可执行文件、`_internal/`、项目许可证、依赖许可证、协议文档、源码快照和 `build-info.json`。`SOURCE.tar.gz` 只用于对应构建的源码核对。

## 验收

构建后执行：

```powershell
$env:BUGGCRAFT_TEST_PACKAGE = (Resolve-Path dist/buggcraft-node/buggcraft-node.exe).Path
python -X utf8 -m unittest tests.test_portable_package -v
```

Linux 将路径替换为 `dist/buggcraft-node/buggcraft-node`。验收会把包复制到带空格的临时目录，从无关工作目录启动，验证首次 HTTPS 向导、协议页、管理员登录、真实 SSH 监听、重启后的节点身份和故障日志。未设置环境变量时，用例明确跳过，不会把源代码测试伪装成打包验收。

发布前还应在干净的 Windows 10/11、Windows Server 2016+ 和目标 Linux 发行版上手动启动一次，确认防火墙提示、浏览器向导、证书指纹、端口占用和日志路径。Windows 签名需要单独的代码签名证书或受控签名服务；当前构建的 `build-info.json` 明确写入 `signed: false`，不能把 SHA256 校验文件当作签名。未签名包被 SmartScreen 拦截时，程序尚未启动，因此不会有应用日志。

## 发布流程

推送变更或在 [Server regression](https://github.com/vdjango/minecraft-tunnel/actions/workflows/server-tests.yml) 点击 **Run workflow** 后，CI 在 Windows 和 Ubuntu 分别构建并运行打包验收。打开构建详情，在 **Artifacts** 下载对应系统的压缩包及 `.sha256` 文件；开发产物保留 30 天，下载需要登录 GitHub。许可证和依赖说明已包含在发行包内，不需要单独拼接文件。

推送形如 `v1.0.0` 的新标签后，只有服务端测试、浏览器向导、systemd 和两个平台的打包验收全部通过，发布任务才会创建 GitHub Release **草稿**。维护者完成目标设备验收、核对签名状态后点击 **Publish release**；公开 Release 的下载不需要登录 GitHub。不应重用或移动已发布的标签。

签名接入后，应在发布任务中增加签名验证，并把 `build-info.json` 的 `signed` 更新为实际结果；没有签名凭证时不得自动伪造签名状态。
