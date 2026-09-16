# BioDSH 应用图标设计任务

BioDSH：给医生和湿实验科学家用的生信智能体桌面版（Windows / macOS），基于 DeepSeek Harness，口号 "Everything is a plugin. 每一次分析，都是一句话"。
品牌气质：专业、克制、现代（Apple / DeepSeek 那种深色高级感），不要卡通、不要 emoji、不要照片风。
主色可选：深蓝→靛紫渐变（现有主页用 #4d6bfe / #7c5cff），或石墨黑底 + 青绿高光。

已有 4 个初稿在 concepts-claude.html（A 双螺旋 X、B 细胞+对话气泡、C 六边形分子+插件节点、D 螺旋字母 B），可以参考、改进或另起炉灶。

## 交付（全部矢量优先）
1. `icon.svg`：1024×1024 主图标，圆角方形底（macOS Big Sur 风格，圆角半径约 22.5%），图形居中、留出安全边距；只用 SVG 基本元素（path/rect/circle/linearGradient），不引用外部资源、不用字体。
2. `icon-mono.svg`：单色版（白色图形、透明底），用于深色标题栏 / 网站 logo。
3. `icon-small.svg`：为 16–32px 优化的简化版（去掉细节，线条更粗）。
4. `make_icons.py`：用本机 Python 生成 `out/icon-{16,32,48,64,128,256,512,1024}.png`、`out/icon.ico`（Windows，含 16/24/32/48/64/128/256）、`out/icon.icns`（macOS，用 iconutil 不可用时手写 icns 容器：ic07/ic08/ic09/ic10 等 PNG 块）。SVG 转 PNG 可用 cairosvg（若未安装，用 `pip install cairosvg`；不行就用 Chrome 无头模式渲染：`"C:\Program Files\Google\Chrome\Application\chrome.exe" --headless=new --screenshot`）。
5. `preview.html`：把三个 SVG 在 512/128/64/32/16 尺寸、浅色和深色底上并排展示，便于验收。
6. `README.md`：设计说明（概念、配色、为什么在小尺寸可辨识）。

## 要求
- 图形在 16px 下仍能认出主形状；在 32px 下不糊成一团。
- 不要文字（不要写 BioDSH 字样在图标里），可以用字母形态作图形（如 B）。
- 至少给出 2 个方向各 1 个成品（放在 `alt/` 下：alt/xxx.svg），主推荐做成上面的 icon.svg。
- 完成后运行 make_icons.py 生成 out/，并确认 preview.html 能打开。
