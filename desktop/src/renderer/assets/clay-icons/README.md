# 陶土文件夹

`folder-terracotta-v1.png` 是根据用户提供的文件夹轮廓和项目现有橙色陶土环材质，使用内置 `image_gen` 生成的透明 PNG。

保留左侧页签和打开的文件夹轮廓，采用暖橙陶土、厚圆边与矿物颗粒。原始图片未经改色或缩放，生成提示词见 `folder-terracotta-v1.prompt.json`。

根据用户反馈，新增 `folder-oat-v1.png`，由内置 `image_gen` 在原图基础上改为低饱和灰褐燕麦陶色，保留形状和透明背景。编辑提示词见 `folder-oat-v1.prompt.json`，原橙色稿留作素材。

0.28.3 仅在当前项目卡片中通过 `ClayFolder.tsx` 显示中性色陶土文件夹（34px），以相邻文本提供可访问名称。打开项目、最近项目及输入区使用低调的线性图标，减少立体元素重复。构建时将中性色图片复制到 `dist/renderer/clay-folder.png`；原有点击和禁用逻辑保持原样。
