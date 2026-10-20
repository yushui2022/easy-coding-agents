# ECA 子 Agent 陶土标志

这组素材以用户提供的橙色折叠陶土环为风格参考，使用内置 `image_gen` 分别生成六张新图。保持细颗粒哑光材质、柔和折面、左上方光线和独立镂空轮廓，改变几何与颜色。

六张均为 **1254 × 1254 RGBA PNG**，透明背景，原始 alpha 保留；没有通过后期抠图、染色或缩放替代生成。每张约 1.3–1.6 MB，精确大小、尺寸和 SHA-256 见 [manifest.json](manifest.json)。完整提示词见 [prompts.json](prompts.json)。

| 素材 | 形状与颜色 | 角色搭配建议 |
|---|---|---|
| [square-blue.png](square-blue.png) | 雾蓝 · 方环 | 编码 |
| [circle-sage.png](circle-sage.png) | 鼠尾草 · 圆环 | 检索 |
| [triangle-lavender.png](triangle-lavender.png) | 淡紫 · 三角 | 规划 |
| [hexagon-honey.png](hexagon-honey.png) | 蜜黄 · 六边 | 测试 |
| [doubleloop-coral.png](doubleloop-coral.png) | 珊瑚 · 双环 | 协作 |
| [quatrefoil-teal.png](quatrefoil-teal.png) | 青绿 · 四瓣 | 审查 |

## 使用建议

- 任务列表头像可以使用 40–56 CSS px；本次总览实测 48 px，在暖白与深色背景上均能区分轮廓。
- 橙色欢迎插画继续保留。此组适合子 Agent 身份或任务类型标志，角色对应只是建议，不代表项目已新增六种固定 Agent。
- 同一个子 Agent 应保留同一个标志；运行、待审批、完成、失败应使用旁边的状态文字/标记表达，不单靠图案或颜色。
- 有角色文字时图片使用空 alt，避免重复朗读；单独作为操作入口时为控件提供可访问名称。
- 为实际列表接入时另做轻量分发资源，保留此处原始文件；不要让大量行重复解码原始大图。

## 预览与验证

- 总览：仓库 `output/design/agent-marks/index.html`，可切换深浅底色。
- 总览截图：`agent-marks-light.png`、`agent-marks-dark.png`，同目录。
- 用独立隐藏 Electron 窗口渲染本地 HTML，确认 12 个图像实例加载成功、无横向溢出；六张大图和六个 48 px 示例均已人工检查。
- `preview-check.json` 记录图像尺寸和布局结果。预览不调用 Agent 模型接口，也未操作用户现有桌面窗口。

0.29.0 已接入主对话子 Agent 行内入口与右侧执行记录。按父会话的子 Agent 创建顺序依次使用六个标志；同一子任务在对话入口、详情和恢复后保持同一标志。图案不代表固定角色，任务职责与执行状态以实际文字为准。六张 PNG 由构建器作为本地资源打包，深浅主题共用透明原图。

