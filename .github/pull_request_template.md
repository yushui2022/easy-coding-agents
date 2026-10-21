## 这个 PR 做了什么

<!-- 一两句说清改了什么、为什么要改 -->

## 怎么验证的

<!-- 贴你实际跑过的命令和结果。跑不了就写跑不了，不要写"应该可以" -->

- [ ] `python -B -m pytest -q`
- [ ] 桌面核心回归（`test_desktop_rpc` 等，见 CONTRIBUTING.md 第 3 节）
- [ ] `npx tsc --noEmit`
- [ ] `node tests/execution-ui.cjs`（`renderer_errors` 为空、`paid_api_calls` 为 0）

## 影响面

- [ ] 改了工具执行 / 审批 / 文件写入（涉及基线、撤销链路）
- [ ] 改了上下文预算 / 压缩
- [ ] 改了桌面协议（`eca/desktop_rpc.py`）或主进程白名单
- [ ] 改了界面（附截图，浅色 + 深色）
- [ ] 只是文档 / 测试

## 关联

<!-- 关联的 Issue：Fixes #123 -->
