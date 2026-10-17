# v0.11：可选执行隔离与本地源码索引

本轮分别增强命令执行边界和大仓库的定位能力。Docker 后端目前标记为实验性；本机 Docker Linux 引擎未启动，因此不宣称真实容器隔离已经验收通过。

## Docker 隔离模式

```powershell
eca --sandbox docker --sandbox-image python:3.11-slim --accept-edits --allow-shell -p "修复功能并运行测试"
```

需要用户事先准备可信的本地 Linux 镜像，包含 `/bin/sh`、`cp`、支持 `-k` 的 `timeout` 及项目所需工具/依赖。示例镜像不代表已经包含 pytest 或业务依赖。推荐使用团队审核过的镜像摘要。ECA 不会自动拉取镜像、启动 Docker Desktop 或下载虚拟磁盘。

- 仅允许本地 Unix socket / Windows named pipe Docker 上下文，显式绑定该 endpoint；引擎不是 Linux、不可用或镜像缺失时拒绝执行，无宿主机回退。
- Git 感知的源码副本最多 20,000 文件、单文件 2 MB、总计 50 MB。排除 Git/会话/缓存/忽略文件、常见凭据路径；发现当前模型密钥的文件会阻断复制。
- 挂载的只有只读副本。原项目、用户主目录、Docker socket、宿主机环境变量都不传入容器；常见代理环境变量显式清空。
- 容器禁网、只读根文件系统、非 root 用户、移除全部 capabilities、禁止获取新权限；限制为 1 CPU、512 MB 内存、128 个进程。工作目录和临时目录分别为 128 MB / 64 MB tmpfs。
- 每条命令在 `/workspace` 的新副本里执行。修改和缓存不会写回项目，也不会传给下一条命令。需要保留的代码变更必须使用正常的 write/edit/delete 工具，继续审批和记录撤销信息。
- 容器内看门狗限制命令时间，终止宽限 5 秒；宿主机超时/取消后另行清理唯一名称的容器。清理无法确认会明确报错，不报告成功；Docker 服务异常时仍可能需要按报告的名称人工清理。
- 此模式下 MCP 和 LSP 暂时禁用，避免另起宿主机进程绕过边界。并行隔离子任务仍禁止 Shell。恢复会话保留已选择的 Docker 模式。
- `--allow-shell` 仍需显式授权。默认 `sandbox=none` 保持宿主机行为，不能因为安装了新版本就假定默认隔离。

这不是虚拟机隔离、企业强制策略或完整 DLP。Docker daemon、宿主机内核及所选镜像属于信任边界；仅使用没有自定义持久卷等额外写入面的可信镜像。凭据规则无法识别任意文件里的所有秘密。模型推理 API 在宿主机正常联网，源码上下文仍发送到所配置的模型服务，容器禁网不代表模型离线。

设计依据：[Docker run 官方选项](https://docs.docker.com/reference/cli/docker/container/run/)。

## 本地增量源码索引

交互命令无需模型请求：

```text
/search verified_run
/map OrderService
```

模型也可调用 `code_search(query, limit)` 与 `repo_map(query, limit)`，code/plan 模式可用，chat 模式拒绝。

- SQLite FTS5 全文排名检索路径与代码，返回文件、匹配行号、短文本及内容指纹。不是向量检索。
- Python 使用 AST 提取类、函数和导入；其他语言仅提供词法线索。导入摘要不是解析完成的依赖图，跨语言引用仍需 LSP/阅读源码确认。
- 索引存于 `.eca/code-index.sqlite3`，通过文件元数据检测变化并更新内容；删除或变为 Git 忽略的旧记录会移除。返回结果前重新核对内容哈希，避免输出已经变化的候选代码。
- 单文件最多 1 MB、扫描字节预算 100 MB、枚举最多 100,000 文件；非 Git 回退枚举有更低限制。达到保守覆盖阈值会显示 `partial`，二进制/过大文件显示跳过计数。输出受条数与字符预算限制，削减结果时标记 `output_truncated`。
- 缓存含源码明文，沿用 `.eca/` 的本地访问和忽略规则；不应提交 Git。扫描元数据仍有开销，不保证所有大型仓库都能瞬间返回。
- 验收/项目记忆的源码指纹上限同步扩大到 20,000 文件、50 MB，单文件仍为 2 MB。超限返回未知，不把不完整指纹当作验证成功。

## 验证范围

2026-10-17：最终全量 **204 passed, 2 skipped**（643.70 秒）；其中真实 Docker 验收因未显式启用、引擎未运行而跳过。最终专项 **27 passed, 1 skipped**。全量命令：`python -B -m pytest -q -p no:cacheprovider --basetemp G:\DevCache\Temp\easy-coding-agents\v011-full`。所有测试均未调用付费模型。

离线测试检查 Docker 参数、后端缺失不回退、远程上下文拒绝、审批和模式限制、超时/取消清理、恢复时保留隔离设置；检查 3,000 文件索引、增量复用、修改/删除/忽略失效、凭据过滤和符号行号。

真实 Docker 验收另提供显式入口（镜像需包含 Python）：

```powershell
$env:ECA_SANDBOX_TEST_IMAGE = "your-preinstalled-trusted-image"
python -B -m pytest -q tests/test_sandbox_index.py -k real_container_boundary
```

该检查验证非 root、无有效 capabilities、无默认网络路由、无法修改只读输入/根目录，以及容器修改不影响宿主机源文件。本轮因引擎未运行而跳过；它也不能替代容器逃逸审计。

本机实际执行入口预检返回 `A running Linux Docker engine is required; no host fallback`，确认走拒绝路径。结果保存在 `output/release/v011-sandbox-preflight.json`。

本仓库检索冒烟：146 个文件进入索引、1 个文件跳过；首次约 2.064 秒，第二次约 1.681 秒且更新数为 0。时间仅代表这台机器和这次运行，不是大型仓库性能承诺。原始结果保存在 `output/release/v011-index-smoke.json`。

输出预算另行检查：设置 700 字符预算并请求 50 项，实际返回 499 字符的有效 JSON、1 项结果，`output_truncated=true`。

v0.11.0 wheel 的 25 个 `eca` 运行时模块与源码逐字节一致。SHA256：
`66b086f56e32f2c2ac42584e17ffdf2423f209a86baca8d005b9e7b008a3695d`。
