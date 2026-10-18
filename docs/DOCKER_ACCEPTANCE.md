# 真实 Docker 隔离验收

需要已运行的本地 Linux Docker 引擎和预先安装的可信 python:3.11-slim 镜像，也可用 ECA_DOCKER_IMAGE 指定同等兼容镜像。测试绝不自动拉取镜像。

```powershell
$env:ECA_TEST_TMP='G:\DevCache\Temp\easy-coding-agents\tests'
$env:TEMP=$env:ECA_TEST_TMP
$env:TMP=$env:ECA_TEST_TMP
$env:ECA_DOCKER_LIVE='1'
python -B -m pytest tests/test_docker_live.py -v
```

测试构造独立临时项目，通过真实 sandbox 路径执行探针：宿主源文件不变、只读输入和根文件系统、凭据文件过滤、非 root 用户、有效 capabilities 为零、只有 loopback 网络接口、超时后清理，以及容器实际启动后的取消清理。每次清理后额外 inspect 确认容器不存在。无操作系统沙箱的宿主执行不会被用作后备方案。

默认全量测试跳过这四项；跳过不代表验收通过。另有 `tests/test_sandbox_index.py` 的真实容器测试，通过 `ECA_SANDBOX_TEST_IMAGE=python:3.11-slim` 开启。Docker 数据、镜像与临时目录均放在 G 盘。

取消测试先确认容器实际运行，并通过 Docker inspect 核对 512 MiB 内存及总内存/交换空间上限、1 CPU、128 个进程、只读根文件系统和禁网配置，再取消并确认容器已移除。另测不存在的随机镜像，要求立即拒绝、不拉取镜像、不回退宿主命令。运行记录区分 `cancelled` 与未确认执行状态；清理状态独立保存。

这组验收不覆盖所有内核逃逸、所有网络攻击或完整企业安全策略；通过也不代表绝对隔离。

## 2026-10-18 实测环境与结果

Windows 11、Docker Desktop 4.91.0、Linux Engine 29.8.0、WSL2；数据盘在 `G:\Data\Docker\wsl\disk\docker_data.vhdx`。使用 `python:3.11-slim`，拉取摘要为 `sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce`。镜像由维护者明确预装，验收脚本和运行时均不自动拉取。

首轮三项失败：两项因 inspect 的小写 `no such object` 提示与断言大小写不一致，一项因非 root 用户对 `/root/.ssh` 的访问被拒绝。修正验收脚本，使“缺失或无权访问”均满足凭据路径不可访问的要求；保留对有效 capabilities、NoNewPrivs、源文件和根目录写保护的检查。随后隔离及相关专项 25 项通过，包含上述三项和原有一项真实容器测试。

最终开启 `ECA_DOCKER_LIVE=1` 和 `ECA_SANDBOX_TEST_IMAGE=python:3.11-slim` 运行 `python -B -m pytest -q`：**271 passed、1 skipped，174.79 秒**。四项新真实 Docker 验收及原有一项真实容器测试均通过；剩余跳过不属于这五项。测试后 `docker ps -a --filter name=eca-` 无输出，无遗留 ECA 容器。本轮未调用模型 API。

## Windows 启动故障

本机从 Codex 桌面环境启动 Docker 时复现 `sailor-ingest.sock` 无法重命名；从 Windows 开始菜单启动后，约 28 秒引擎就绪，连续三次连接检查通过。安装清单与 [Codex MSIX/AppData 问题报告](https://github.com/openai/codex/issues/52698) 一致，启动环境是首要怀疑原因；一次对照不等于底层原因已完全证明。

遇到这种情况，先从开始菜单启动 Docker，等待引擎就绪，再使用 ECA。ECA 不自动启动、重置 Docker 或删除其 socket，也不退回宿主执行。G 盘迁移备份保留，未修改原 Ubuntu 注册。此验收只覆盖这一 Windows/WSL2 环境，不代表所有平台已验收。
