# 墨水屏时钟 - 服务端

> 对应 **W5 里程碑**：完整 4 区界面 + 创意功能

把 ESP32 不擅长的"画图"工作从芯片上搬到 PC 上：服务端用 Pillow 渲染 PNG，ESP32 只负责"取 + 刷"。本目录是**服务端全部代码**。

---

## 🚀 启动

```bash
# 1) 装依赖（家里 PC 第一次需要）
pip install -r requirements.txt

# 2) 启动
python app.py

# 3) 浏览器打开
#    http://localhost:5000/preview      ← 模拟墨水屏看效果
#    http://localhost:5000/api/screen   ← 实际 PNG（ESP32 也拉这个）
#    http://localhost:5000/api/info     ← 当前数据 JSON（调试用）
```

> ⚠️ Windows 自带中文字体（微软雅黑 msyh.ttc），不需要额外下载。
> Linux/macOS 需要装一个 CJK 字体（参考 `renderer.py` 的 `FONT_CANDIDATES_*`）。

---

## 📁 文件结构

```
server/
├── app.py              # Flask 入口（路由 ~50 行）
├── renderer.py         # Pillow 渲染核心（4 区布局）
├── data.py             # 模拟数据层（时间/天气/古诗/倒计时）
├── templates/
│   └── preview.html    # 浏览器模拟墨水屏的前端
├── requirements.txt
└── README.md
```

---

## 🎨 4 区布局（400 × 300）

```
┌──────────────────────────────────────────┐ y=0
│ 6月21日 周日                  北京       │ ← 顶部栏
├──────────────────────────────────────────┤
│                                          │
│              10:35                       │ ← 时间（主区）
│                                          │
├──────────────────────────────────────────┤
│ ☀ 26° 晴  体感27°                        │ ← 当前天气
│ 湿度 45%   东南风 2级                    │
├──────────────────────────────────────────┤
│ 今  一  二  三  四  五  六  日            │
│ ☀  ☁  ☂  ⚡  ☁  ☀  ☀                   │ ← 7 日天气
│ 28°/19° 26°/18° 23°/17° ...             │
├──────────────────────────────────────────┤
│     「少年辛苦终身事，莫向光阴惰寸功」    │ ← 古诗
├──────────────────────────────────────────┤
│       🎂妈妈生日 86天  🏖暑假 24天       │ ← 倒计时
└──────────────────────────────────────────┘ y=300
```

每个区在 `renderer.py` 里有独立函数，改一处不影响其它：
- `draw_top_bar()` - 顶部
- `draw_time()` - 时间
- `draw_current_weather()` - 当前天气
- `draw_weekly_forecast()` - 7 日
- `draw_poem()` - 古诗
- `draw_countdown()` - 倒计时

---

## 🔌 ESP32 端怎么对接

ESP32 端代码不用改任何东西！只要把 `clock.py` 里的 `SERVER_URL` 改成 PC 的 IP：

```python
SERVER_URL = "http://192.168.1.100:5000/api/screen"
```

> 怎么查 PC 的 IP？Windows: `ipconfig`，Mac/Linux: `ifconfig`。
> 手机/平板用 `http://192.168.1.100:5000/preview` 也能看效果（要在同一 WiFi 下）。

---

## 🧪 改点东西立刻看效果

| 想改什么 | 改哪个文件 | 哪个函数 |
|----------|-----------|---------|
| 时间字号 | `renderer.py` | `load_fonts()` 里 `"time_big": 64` |
| 城市名 | `data.py` | `current_weather()` 里 `"city": "北京"` |
| 加一首古诗 | `data.py` | `POEMS` 列表里加一行 |
| 加一个倒计时 | `data.py` | `IMPORTANT_DATES` 里加一行 |
| 7 日天气数据 | `data.py` | `WEEKLY_FORECAST` |
| 区域位置 | `renderer.py` | 各 `draw_xxx()` 里的 y 坐标 |

改完保存，**浏览器点 "立即刷新"**（或等 60 秒自动），立刻看到变化。
**不用烧固件**——这就是服务端架构最大的好处 ✅

---

## 🔄 之后想接真实数据？

只需改 `data.py` 一个文件：

```python
# 比如接 wttr.in（免费无需 Key）
import requests
def current_weather():
    r = requests.get("https://wttr.in/Beijing?format=j1", timeout=5).json()
    return {
        "city": "北京",
        "temp": int(r["current_condition"][0]["temp_C"]),
        "cond_cn": r["current_condition"][0]["lang_zh"][0]["value"],
        ...
    }
```

`renderer.py` 不动一行。

---

## 🛡️ 安全提醒

- 服务端只在内网用（`bind 0.0.0.0`），**不要**直接暴露到公网
- 路由器上关掉 5000 端口的外网访问
- 以后想从外网看，套一层 SSH 端口转发或 Cloudflare Tunnel

---

## 🐛 调试清单

| 现象 | 原因 | 解决 |
|------|------|------|
| 浏览器访问 /preview 是空白 | 服务端没启动 / 端口被占 | 看终端有没有 `Running on http://0.0.0.0:5000` |
| 中文显示成方块 | 系统没装 CJK 字体 | 装一个中文字体（Win/macOS 默认都有） |
| 浏览器一直转圈 | 字体加载慢（首次） | 第二次刷新会快很多 |
| ESP32 拉不到图 | IP/端口不对，或 Windows 防火墙挡了 | `ipconfig` 查 IP；防火墙允许 5000 |
| PNG 是灰的不是黑白 | `renderer.py` 里没转 1-bit | 看 `render()` 最后一行 `.convert("1")` |

---

## 📊 给儿子的"为什么这么写"

> **Q: 为什么时间字号 64 最大？**
> A: 400 像素宽，字号 64 的话"10:35" 5 个字大概 200 像素，居中正好。更大的话要么换行要么挤压。

> **Q: 为什么先在 L 模式画再转 1-bit？**
> A: L 模式（灰度）可以让文字"反锯齿"，边缘平滑；最后转 1-bit 一次性变黑白。比直接在 1-bit 模式画清晰得多。

> **Q: 为什么每分钟刷一次不是每秒？**
> A: 屏幕上的分钟只在你看的那一瞬间才变；服务端每次都返回最新画面，但 ESP32 每 60 秒才拉一次。客户端控制刷新节奏 = 节省 WiFi 流量 + 屏幕寿命。
