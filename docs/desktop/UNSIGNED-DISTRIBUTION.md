# 未签名分发说明（Windows x64）

本项目的安装包**没有做代码签名**（`desktop/package.json` 中 `signExecutable: false`）。这只影响 Windows 的安全提示，不影响程序本身。给同事、朋友或自己团队安装时，按本文操作即可。

适用于 0.34.2 及之后的手工分发。它不是代码签名证书的替代方案，也不改变程序的安全边界。

## 1. 安装时会被拦一次

双击 `ECA-Desktop-<版本>-x64-Setup.exe` 后，可能看到蓝色的「Windows 已保护你的电脑」：

1. 点「更多信息」
2. 点「仍要运行」
3. 选择安装目录（默认按用户安装，**不需要管理员权限**）

出现拦截的原因是 Windows 不认识发布者，不代表文件被篡改。判断文件是否被篡改请用下一节的哈希校验，不要靠提示框。

## 2. 校验下载的完整性

发布页会附带 `SHA256SUMS.txt`。在 PowerShell 里核对：

```powershell
Get-FileHash -LiteralPath '.\ECA-Desktop-0.34.2-x64-Setup.exe' -Algorithm SHA256
```

输出必须与 `SHA256SUMS.txt` 中同一文件名的值逐字一致。不一致就不要安装，重新下载。

只从发布页下载。通过聊天工具、网盘转发的同名文件没有这个保证。

## 3. 第一次启动要配一个模型

程序不自带账号、额度或试用。首次打开是欢迎页，需要「模型与设置 → 添加连接」，填三项：

- API 地址（OpenAI 兼容、Responses 或 Anthropic Messages 任一协议）
- API 密钥
- 模型 ID（必须支持工具调用）

本机 ollama 之类只要支持工具调用也可以填。密钥用 Windows DPAPI（Electron safeStorage）加密，**与当前 Windows 账户绑定**：换机器或换账户需要重新填，把 `preferences.json` 拷给别人也用不了。

## 4. 数据放在哪里

| 内容 | 位置 |
| --- | --- |
| 模型连接与加密密钥 | 有 G 盘：`G:\Data\ECA\Desktop`；没有 G 盘：`%APPDATA%\eca-desktop` |
| 项目会话、修改快照、附件 | 每个项目自己的 `.eca` 目录 |
| 运行缓存 | 同目录下的 `cache`，可用 `ECA_DESKTOP_CACHE_HOME` 覆盖 |

模型连接目录可用 `ECA_DESKTOP_DATA_HOME` 覆盖。备份项目时要把该项目 `.eca` 里的 `attachments` 一起带走，那不是缓存。

卸载程序**不会**删除这些数据（`deleteAppDataOnUninstall: false`），需要自己清理。

## 5. 安全边界（给使用者看的真话）

- **不是沙箱**：模型执行的 shell 命令以你自己的 Windows 账户权限运行，可以访问项目外的文件和网络。文件修改有差异预览、冲突检查和撤销记录，但 shell 的副作用不在快照范围内。
- 实验性的 Docker 隔离要求本机已有 Linux 引擎并预装可信镜像，且禁用联网工具；后端缺失时不会降级到宿主机执行。
- `web_fetch` 只读公网页面，每次授权，有正文上限；它不会访问你的本地服务。
- 会话和快照留在本地，但发给模型的上下文会交给你配置的那个 API。

## 6. 杀毒软件误报怎么办

PyInstaller 打包的可执行文件（`resources\backend\ECA Desktop Backend.exe`）偶尔被误报。先按第 2 节核对哈希：

- **哈希不一致**：不要运行，重新下载，并考虑是不是来源被替换。
- **哈希一致但仍被拦**：基本可以判定为误报。可以：
  1. 在 Windows 安全中心把安装目录加入排除项（仅限你信任的机器）；
  2. 向微软提交误报：<https://www.microsoft.com/en-us/wdsi/filesubmission>（选择「软件开发者」，上传安装包或 `ECA Desktop Backend.exe`，说明这是 PyInstaller 打包的开源项目、附上 SHA256 与发布页地址）。
- 不要为了安装而全局关闭 SmartScreen 或实时保护。

## 7. 更新

没有自动更新功能。新版本需要手动下载安装包，在**原位置覆盖安装**（安装前退出应用）。覆盖安装保留模型连接、会话和项目数据。

版本号同时出现在 `package.json`、`desktop/package.json`、`pyproject.toml` 和 `eca/__init__.py` 里，本文件随版本更新。
