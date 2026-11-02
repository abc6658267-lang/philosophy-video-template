# 哲学系列 · 开场模板

结构：引子"今天我们要讲的是"（1.6 秒）→ 概念轮播（换词卡在转盘咔哒声上，越转越慢）→ 闪黑 0.5 秒 → 揭晓主题（打字动画）

## 每期怎么用
改 config.json 里这几项，然后运行 `python3 make_opening.py config.json`：
- `roulette.words`：轮播的词，最后一个是"停住"的词（建议 6～8 个）
- `roulette.images`：每个词配的背景（从 assets/bg_01～12 里挑，可隔几期换几张）
- `reveal.title`：揭晓的主题
- `reveal.background`：揭晓底画面，填正片第一个镜头的视频（.mp4）或图片

输出：
- opening.mp4：画面 + 转盘音效
- opening_timing.json：配音对齐时间点（"今天我们要讲的是"放在 hook_voice_at，主题配音放在 title_voice_at）
- 揭晓底用的是正片第一个镜头视频时，正片从该镜头的第 reveal_video_used_seconds 秒接着放

## 引子动画（神经网络）
`hook.anim` 打开后，引子画面上会从一个点（人物头顶）长出一张发光的神经网络，信号沿连线流动，表示"思绪升起"。
- `type`: 填 `"neural"` 打开；删掉 `anim` 就是原来的静态推镜
- `origin`: 起点位置（画面比例坐标 0～1）。默认值 `[0.82, 0.553]` 对应 hook_01.jpg 里人物的头顶（按 1440×1080 构图）；换引子图或换画面比例时要重新对一下
- `spread`: 网络展开的范围（画面高度的比例），`nodes`: 节点数，`angles`: 向哪些方向展开（-90 为正上方）
- `grow`: 网络长满所需秒数，`color`: 发光颜色，`seed`: 换个数字可以换一种网络形状
- 引子时长建议 2.4 秒（`hook.duration`），让动画有时间展开
- `hook.image` 也可以填视频（.mp4），引子底画面就会用视频

## 可调参数
- `roulette.sfx_speed`：转盘音效加速倍数（1.25 = 轮播约 1.8 秒；调大更快）
- `roulette.last_word`：最后一个词停留时长（含渐暗）
- `black`：闪黑时长
- `grade`：统一调色（对比度、暗角）
- `style.shadow_color` / `style.skew`：投影颜色、斜体角度
- 不填 `click_sfx` 时，自动用代码合成的咔哒声

## 素材版权
assets/credits.csv 列出了每张图的来源。其中标 CC BY 的图片（hook_03、bg_01、bg_02、bg_04、bg_08、bg_10、bg_11）需要署名，在视频简介里写一行"开场图片来源：Wikimedia Commons（作者见 credits）"即可；CC0 / 公有领域 / Pixabay 的不用署名。
