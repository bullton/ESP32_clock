# 表情字体（可选）

墨水屏是 1-bit 单色屏，渲染器默认把 emoji 按 `symbols.py` 里的降级表
替换成可显示的文字或符号。

如果想让真实 emoji 字形上屏，在这个目录放一个**单色 outline** 字体即可，
文件名随意（`.ttf` / `.otf`）：

- Noto Emoji（推荐，单色，OFL 授权）
- Symbola
- 其他包含 emoji 轮廓的字体

放好后重启服务，渲染器会自动检测并优先使用该字体；此时底栏文本不再做
emoji 降级。

注意：彩色 emoji 字体（如 NotoColorEmoji.ttf、Segoe UI Emoji）是位图/COLR
格式，Pillow 在 1-bit 画布上无法正确输出，使用了也可能只剩空白，因此不推荐。
