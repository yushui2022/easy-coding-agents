# 输出与持续执行配置

主 Agent 的 `max_turns` 和 `output_recovery_limit` 默认均为 0，表示不限响应轮数和截断恢复次数。用户可以 Ctrl+C 中断；已完成修改保留。正整数仍可用于限制自动化任务，旧配置中的显式值不会被覆盖。

```powershell
ecs --max-turns 0 --output-recovery-limit 0
```

官方 HTTPS DeepSeek 端点上的 deepseek-flash / deepseek-v4-pro，在没有显式配置时采用 393216 输出 tokens 和 1048576 上下文 tokens。依据：[官方模型元数据](https://api-docs.deepseek.com/api/list-models/)，核对日期 2026-10-18。用户指定较小上下文窗口时，自动输出额度不超过该窗口的一半；最终配置仍须留出输入和预留空间。

未知模型和代理端点仍使用通用默认值 8192 / 32768，不猜测代理能力。可通过 `--max-output-tokens`、`--context-window-tokens` 或同名 TOML 字段覆盖。模型配置档案也遵循显式值优先；会话内 `/model NAME` 保留当前额度，切换配置档案 `/model @PROFILE` 则重新计算该档案默认值。

输出额度是上限，不要求模型每次写满。服务端仍可能截断；Agent 会请求拆分剩余步骤，保留此前完成的修改，丢弃不完整响应中的工具调用。自动恢复不能保证模型最终成功；取消仍然有效。

子 Agent 的轮数与超时、重复工具调用检测、用户配置的共享请求预算、网络重试与上下文保护仍有效。工具日志的 `output_limit` 是日志裁剪长度，与模型生成上限无关。
