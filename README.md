# 🌟 4.2寸墨水屏智能时钟 - 项目说明

> **爸爸 + 10岁儿子 + 8岁女儿**
> 硬件：4.2寸墨水屏 HAT V2 + ESP32-S3 N16R8
> 软件：MicroPython + 自研 V2 驱动
> 架构：**服务端 Pillow 渲染 → 15000 字节原始位图 → ESP32 直接刷屏**
> 总预算：~¥130
> 预计周期：8-10 周（每周 3-4 小时）

> **配套文档**：
> - 📋 [PLAN.md](./PLAN.md) — 项目方案（学习路径、分工、敏捷开发、附录）
> - 📊 [STATUS.md](./STATUS.md) — 项目当前状态看板

---

## 📋 目录

1. [项目总览](#一-项目总览)
2. [硬件清单](#二-硬件清单)
3. [软件栈与架构](#三-软件栈与架构)
4. [代码资源库](#四-代码资源库)
5. [服务端接口约定](#五-服务端接口约定)
6. [安全与注意事项](#六-安全与注意事项)
7. [常见问题 Q&A](#七-常见问题-qa)

---

## 一、项目总览

### 🎯 项目目标
从零开始，用 8 周时间，父子三人共同完成一个**带 Wi-Fi 联网的电子墨水屏智能时钟**，能显示时间、日期、天气、每日古诗。

### 🌈 项目愿景
- **爸爸**：技术引导、安全把关、AI 协作
- **儿子(10岁)**：主力 Python 编程、硬件调试、服务端开发
- **女儿(8岁)**：美术设计、创意内容、UI 装饰

### 💡 核心理念
> "我们一起完成一件很酷的事"

不是教孩子学编程，而是**一起探索、一起创造**。每个孩子都做自己擅长的事，遇到困难全家一起想办法。

### 📚 文档导航

| 文档 | 作用 | 何时看 |
|---|---|---|
| **README.md**（本文）| 项目"是什么"：硬件、架构、代码、服务端约定 | 第一次接触项目 |
| [PLAN.md](./PLAN.md) | 项目"怎么做"：8 周计划、分工、方法、附录 | 每个 Sprint 开始前 |
| [STATUS.md](./STATUS.md) | 项目"到哪了"：当前进度、任务、Bug、积分 | 每天 / 每周更新 |

### 🏛️ 关键架构决策

> **服务端渲染 + 原始位图传输**（v3.0）
>
> ESP32 不解析任何图像格式。服务端用 Pillow 渲染好 400×300 画面，二值化成单色位图，位翻转后**直接打包成 15000 字节二进制流**。ESP32 收到后**不解码、直接刷屏**。
>
> **好处**：
> - ESP32 端零依赖（不需要 PNG 解码库）
> - 抗锯齿灰度渲染 + Floyd-Steinberg 抖动 → 文字边缘平滑
> - 固定 15000 字节传输，~1 秒拉取
> - ESP32 代码 ~70 行，bug 面积小
>
> 详见 [§ 三、软件栈与架构](#三-软件栈与架构)

---

## 二、硬件清单

| 序号 | 物品 | 型号 | 价格 | 数量 | 备注 |
|---|---|---|---|---|---|
| 1 | 4.2寸墨水屏 | 4.2inch e-Paper **HAT V2** | ¥90-100 | 1 | **必须V2版**（带V2标签），支持局刷 |
| 2 | 主控 | ESP32-S3 N16R8 开发板 | ¥28 | 1 | Type-C 接口，16MB Flash + 8MB PSRAM |
| 3 | 杜邦线 | 8P 母对母 20cm | ¥3 | 2条 | 连接屏幕8Pin排针 |
| 4 | 数据线 | Type-C | ¥0 | 1 | 家里找，**必须能传数据** |
| 5 | 相框/外壳 | 4寸相框或纸盒DIY | ¥10-20 | 1 | 最后做外壳时用 |
| **合计** | | | **~¥130-150** | | |

### 🔌 引脚连接图

```
4.2寸墨水屏 HAT V2    普中ESP32-S3开发板
┌─────────────┐         ┌──────────────┐
│ VCC (红)    │─────────│ 3.3V         │
│ GND (黑)    │─────────│ GND          │
│ DIN (MOSI)  │─────────│ GPIO42       │
│ CLK (SCK)   │─────────│ GPIO14       │
│ CS          │─────────│ GPIO41       │
│ DC          │─────────│ GPIO2        │
│ RST         │─────────│ GPIO4        │
│ BUSY        │─────────│ GPIO5        │
└─────────────┘         └──────────────┘
```

⚠️ **说明**：
- 屏幕型号：**4.2寸墨水屏 HAT V2**（必须V2版）
- 引脚经过实际测试可用，已避开摄像头、LCD等占用
- 实际接线顺序对应代码 `clock.py` 里的 GPIO 分配
- SPI(2) 用软件引脚映射实现

⚠️ **接线铁律**：
- 必须在**断电状态**下接线
- VCC 接 3.3V **不是** 5V（接错会烧屏）
- 排针**插紧**到 ESP32 上

> 💡 **扩展引脚规划**：未来加传感器/语音模块的引脚分配，参见 [PLAN.md - 附录 C 外设扩展全方案](./PLAN.md#附录-c外设扩展全方案)

---

## 三、软件栈与架构

### 🏛️ 系统架构

```
┌──────────────────────────────────────┐
│  服务端 (家里 PC / 树莓派)            │  ← 爸爸 + 儿子开发
│  - Pillow 灰度渲染（抗锯齿）         │
│  - Floyd-Steinberg 抖动二值化        │
│  - 位翻转 + 打包                     │
│  - 输出 15000 字节二进制流            │
│  - HTTP GET /api/screen             │
└──────────────────────────────────────┘
                  ↓ HTTP GET
┌──────────────────────────────────────┐
│  ESP32 (clock.py, ~70 行)           │  ← 极简
│  - 连 WiFi                          │
│  - HTTP 拉 15000 字节                │
│  - 灌进 framebuffer                  │
│  - 调用驱动刷屏                      │
└──────────────────────────────────────┘
                  ↓
┌──────────────────────────────────────┐
│  驱动 (epaper4in2_V2.py)             │
│  - 全刷 / 局刷                       │
└──────────────────────────────────────┘
                  ↓
┌──────────────────────────────────────┐
│  MicroPython 固件                    │
│  - SPI、GPIO、Wi-Fi、HTTP            │
└──────────────────────────────────────┘
```

### 🎨 服务端渲染管线（关键细节）

```
┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Image.new   │ →  │ 加载 .ttf 字体 │ →  │ draw.text() │ →  │ convert('1') │
│ 'L' 模式     │    │ 画时间/天气/古诗│    │ 抗锯齿文字   │    │ 抖动二值化   │
│ 灰度画布     │    │              │    │ 边缘平滑     │    │              │
└─────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
                                                                    ↓
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ HTTP 响应    │ ←  │ 15000 字节    │ ←  │ bitswap()   │ ←  │ tobytes()    │
│ application/ │    │ 原始 buffer   │    │ MSB→LSB     │    │ MSB-first   │
│ octet-stream │    │ 400×300/8     │    │              │    │              │
└──────────────┘    └──────────────┘    └──────────────┘
```

> **核心洞察**：先在灰度模式下画（Pillow 自动抗锯齿），再用 Floyd-Steinberg 抖动二值化，最终的 1-bit 图看起来比"直接 1-bit 画"清晰得多——文字边缘有灰度过渡的"假象"。

### 🔧 工具清单

| 工具 | 用途 | 哪里下载 |
|---|---|---|
| Thonny | MicroPython IDE（孩子用最友好）| thonny.org |
| esptool.py | 烧录固件 | `pip install esptool` |
| MicroPython 固件 | ESP32-S3 系统 | micropython.org/download/ESP32_GENERIC_S3/ |
| 自研 V2 驱动 | 墨水屏驱动 | 本仓库 `epaper4in2_V2.py` |
| Pillow | 服务端图像渲染 | `pip install pillow` |
| Flask | 服务端 HTTP 服务 | `pip install flask` |
| requests | 服务端拉天气 | `pip install requests` |

> 📝 **依赖对比**：v3.0 相比之前版本，**ESP32 端不再需要 pngdec 库**（节省 ~5KB flash），服务端需要 Pillow + Flask + requests。

### 📦 ESP32 端需要传到板子的文件

```
/
├── main.py                # 启动入口（自动执行 clock.main()）
├── clock.py               # 主程序
└── epaper4in2_V2.py       # V2 屏幕驱动（自研）
```

> ✅ **极简**：3 个文件，无第三方依赖。

### 🖥️ 服务端技术栈

服务端用什么技术都行，只要能响应 `GET /api/screen` 并返回 15000 字节原始位图即可。**推荐**：Python + Flask + Pillow（参考 `server.py`）。

```python
# 服务端最小骨架（完整代码见 server.py）
from flask import Flask, Response
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

@app.route('/api/screen')
def screen():
    img = Image.new('L', (400, 300), 255)         # 灰度画布
    draw = ImageDraw.Draw(img)
    # ... 用 Pillow 画时间/天气/古诗 ...
    img_1bit = img.convert('1', dither=Image.Dither.FLOYDSTEINBERG)
    return Response(img_1bit.tobytes(), mimetype='application/octet-stream')
```

> 💡 **设计窍门**：服务端同时暴露 `GET /preview` 路由，返回 PNG 格式给浏览器，**不用烧固件就能调试 UI**。

---

## 四、代码资源库

### 📁 项目文件结构

```
/clock_project/
├── README.md                # 项目说明（本文件）
├── PLAN.md                  # 项目方案（8周计划、附录）
├── STATUS.md                # 项目状态看板
│
├── main.py                  # ⭐ MicroPython 启动入口
├── clock.py                 # ⭐ 主程序：拉 15000 字节位图 + 刷屏
├── epaper4in2_V2.py         # ⭐ V2 屏幕驱动（自研）
│
├── server.py                # ⭐ 服务端：Pillow 渲染 + Flask 暴露
│
├── minimal_test.py          # 早期最小测试（保留作参考）
├── minimal_full_test.py     # 全刷测试
├── test.py / test2.py       # 各阶段测试代码
├── test_partial.py          # 局刷测试
├── test_v2.py               # V2 驱动测试
├── full_black_white.py      # 全黑/全白测试
├── screen_color_test.py     # 颜色测试
├── show_image.py            # 旧：显示图片测试
├── jpg_to_epd.py            # 旧：JPG 转墨水屏数据
│
├── image_dark.py            # 旧：PC 端预渲染深色图片
├── image_light.py           # 旧：PC 端预渲染浅色图片
│
├── epd4in2_V2-demo/         # 官方 C++ demo 参考
└── ESP32_GENERIC_S3-20260406-v1.28.0.bin   # MicroPython 固件
```

### ⭐ 核心代码：`clock.py`（70 行）

```python
import network, urequests, time
from machine import Pin, SPI
import epaper4in2_V2

WIFI_SSID = "你的SSID"
WIFI_PASSWORD = "你的密码"
SERVER_URL = "http://192.168.1.x:5000/api/screen"
BUF_SIZE = 400 * 300 // 8   # 15000

def init_epd():
    spi = SPI(2, baudrate=20000000, polarity=0, phase=0,
              sck=Pin(14), mosi=Pin(42))
    cs   = Pin(41, Pin.OUT, value=1)
    dc   = Pin(2,  Pin.OUT, value=0)
    rst  = Pin(4,  Pin.OUT, value=1)
    busy = Pin(5,  Pin.IN)
    epd = epaper4in2_V2.EPD(spi, cs, dc, rst, busy)
    epd.init()
    return epd

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        for _ in range(20):
            if wlan.isconnected(): return True
            time.sleep(1)
    return wlan.isconnected()

def fetch_bitmap():
    try:
        r = urequests.get(SERVER_URL, timeout=10)
        data = r.content
        r.close()
        return data if len(data) == BUF_SIZE else None
    except Exception as e:
        print("拉取失败: %s" % e)
        return None

def main():
    if not connect_wifi(): return
    epd = init_epd()
    last_full = time.time()
    while True:
        buf = fetch_bitmap()
        if buf:
            force = (time.time() - last_full) > 3600
            if force:
                epd.display_frame(buf)
                last_full = time.time()
            else:
                epd.partial_display(buf, 0, 0, 400, 300)
        time.sleep(60)
```

### ⭐ 核心代码：`server.py`（服务端）

完整源码在仓库 `server.py`，核心逻辑：

```python
# 1. 加载字体
font = ImageFont.truetype("msyh.ttc", 60)

# 2. 灰度渲染
img = Image.new('L', (400, 300), 255)
draw = ImageDraw.Draw(img)
draw.text((20, 10), "10:35", font=font, fill=0)

# 3. 抖动二值化
img_1bit = img.convert('1', dither=Image.Dither.FLOYDSTEINBERG)

# 4. 位翻转 + 打包
buf = bytes(bitswap(b) for b in img_1bit.tobytes())
# buf 长度固定 15000

# 5. HTTP 响应
return Response(buf, mimetype='application/octet-stream')
```

### ⭐ 核心驱动：`epaper4in2_V2.py`

```python
from epaper4in2_V2 import EPD

epd = EPD(spi, cs, dc, rst, busy)
epd.init()                    # 初始化
epd.display_frame(buf)        # 全刷（4 秒闪烁）
epd.partial_display(buf, x1, y1, x2, y2)  # 局刷（0.5 秒无闪烁）
epd.clear()                   # 清屏（全白）
epd.sleep()                   # 休眠省电
```

驱动特性：
- ✅ 全刷（display_frame）：4 秒闪烁，适合启动和清残影
- ✅ 局刷（partial_display）：0.5 秒无闪烁，适合日常更新
- ✅ 兼容 V2 屏幕的 BUSY=1 表示忙逻辑
- ✅ 数据入口模式 X-mode 正确配置

> 📝 **驱动说明**：原 mcauser 库（`epaper4in2.py`）**不兼容 V2 屏幕**（V2 的 BUSY 电平逻辑、数据入口模式、初始化时序都不同）。本项目使用基于官方 EPD_4IN2_V2.cpp 移植的自研驱动 `epaper4in2_V2.py`。

---

## 五、服务端接口约定

ESP32 与服务端通信只有一个端点，约定如下：

### 接口定义

```
GET /api/screen
```

| 项目 | 规格 |
|---|---|
| 方法 | `GET` |
| URL | 自由配置（ESP32 端 `SERVER_URL`） |
| 请求头 | 无特殊要求 |
| 响应 | `Content-Type: application/octet-stream` |
| 响应体 | **15000 字节原始位图**（400×300 / 8）|
| 状态码 | 200 OK |

### 位图格式

| 属性 | 值 |
|---|---|
| 尺寸 | **400 × 300**（严格）|
| 色彩 | **1-bit 单色**（每像素 1 bit）|
| 打包 | **每字节 8 像素，LSB 在左**（`framebuf.MONO_HLSB` 格式）|
| 大小 | 固定 **15000 字节** |
| 0 = 黑 | 1 = 白 |

### 为什么 LSB-first？

Pillow 的 `tobytes()` 默认输出 **MSB-first**（最高位是第一个像素），但 `framebuf.MONO_HLSB` 期望 **LSB-first**（最低位是第一个像素）。因此服务端必须 `bitswap()` 翻转每个字节。

不翻转的后果：**图像水平镜像 + 颜色反转**。

### 调试接口

| 接口 | 返回 | 用途 |
|---|---|---|
| `GET /api/screen` | 15000 字节位图 | ESP32 调用 |
| `GET /preview` | PNG 图片 | 浏览器预览，调试用 |
| `GET /` | HTML 索引 | 入口页 |

### 接口契约（给服务端开发者的提示）

服务端**不应该**：
- 期望 ESP32 会传任何参数（保持 GET 无 body 简单）
- 返回缓存控制之外的内容（每次请求都返回当前时间点的画面）
- 假设客户端有持久连接

服务端**应该**：
- 每次请求都返回"现在应该显示的画面"
- 失败时返回 5xx 状态码（ESP32 会忽略并保持上一帧）
- 响应时间 < 3 秒（避免 ESP32 超时）

### 验证清单

部署后浏览器访问 `http://<PC-IP>:5000/preview`，应该看到一张 400×300 的图片，包含：
- ✅ 左上：大字时间
- ✅ 时间下：日期 + 星期
- ✅ 右上：当前温度 + 描述
- ✅ 中部：7 日天气
- ✅ 底部：一行古诗/新闻

如果显示成镜像 / 颜色反了 → 忘记 `bitswap()` 了。

---

## 六、安全与注意事项

### ⚠️ 必读（爸爸必看）

1. **FPC 排线极脆弱**
   - 8岁女儿操作时**爸爸必须全程在场**
   - 严禁：弯折、撕扯、按压
   - 安全做法：HAT 版排线已焊死，孩子只接 8Pin 排针

2. **电压绝对不能错**
   - VCC 接 3.3V，**不能接 5V**
   - 接线时必须断电
   - 接线完成后**爸爸检查一遍**再通电

3. **屏幕保护**
   - 每次刷新后**必须** `epd.sleep()`
   - 刷新间隔 ≥ 180 秒
   - 避免阳光直射
   - 不用时**断电**
   - **局刷可以连续使用**（不是5次限制）
   - 每隔 1 小时做 1 次全刷清理（避免累积残影）

4. **烧录固件**
   - 烧录时**按住 BOOT 键**再插 USB
   - 松开 BOOT 键后才开始烧录
   - 烧录失败时不要慌，**重试一次**

5. **数据线**
   - 必须用**能传数据**的 Type-C 线
   - 纯充电线（只接 VCC/GND）不行

6. **代码安全**
   - Wi-Fi 密码写在代码里
   - 不要把代码上传到公开 GitHub
   - 教孩子：**密码是隐私**

7. **服务端安全**
   - `/api/screen` 不需要鉴权（内网使用）
   - **不要把端口暴露到公网**
   - 路由器上设防火墙，或服务端只绑 `127.0.0.1` + SSH 端口转发

> 💡 关于局刷策略的完整分析（5 次迷思、推荐策略），见 [PLAN.md - 附录 B 局刷策略详解](./PLAN.md#附录-b局刷策略详解)

---

## 七、常见问题 Q&A

### Q：屏幕不亮？
A：检查 4 件事：电源、SPI 接线、引脚号、固件烧录

### Q：屏幕显示乱码？
A：宽度高度反了。`display_frame()` 用的是 400×300，不要调换

### Q：mcauser 库（V1）能用吗？
A：❌ **不能用**。V1 和 V2 屏幕的 BUSY 电平逻辑、初始化时序、数据入口模式都不同。
请使用本仓库的 `epaper4in2_V2.py`（已验证可用）。

### Q：Wi-Fi 连不上？
A：检查密码、Wi-Fi 是 2.4G（不是 5G）、信号强度

### Q：拉不到数据 / 显示空白？
A：检查 3 件事：
1. 服务端能不能用浏览器访问 `http://<PC-IP>:5000/preview` 看到画面
2. ESP32 的 `SERVER_URL` IP 和端口对不对
3. 服务端返回的字节数**正好是 15000**（可在服务端打印 `len(buf)`）

### Q：图像是镜像的 / 颜色反了？
A：服务端忘记 `bitswap()` 了。每个字节都要位翻转（MSB-first → LSB-first）。

### Q：屏幕残影？
A：局刷可以连续使用，不会"5次后强制清理"。但累积多次后对比度会轻微下降，每隔 1 小时做 1 次全刷清理即可恢复清晰度。

### Q：服务端挂了会怎样？
A：ESP32 拉取失败时**保持上一帧不变**（墨水屏特性：不掉电就一直显示）。
服务端恢复后下个周期自动恢复。

### Q：局刷有什么限制？
A：物理上没有次数限制，**"5次"是经验值不是硬规定**。实际项目中推荐：
- 时钟场景：99% 局刷 + 1次/小时 全刷
- 视觉效果接近完美无闪烁
- 比每分钟全刷好 60 倍体验

### Q：文字边缘看起来"毛糙"？
A：✅ 正常现象。这是墨水屏的 1-bit 抖动效果。
想要更平滑：在服务端把字体渲染得更大（4 倍 → 缩小到目标尺寸），抖动效果会更好。

### Q：孩子失去兴趣怎么办？
A：停下当前任务，做点简单的。比如让他设计图标、装饰外壳。
服务端架构下，让孩子在浏览器里调样式比改 Python 直观得多。

> 💡 更多 W1-W8 每周具体行动、Bug 追踪模板、风险登记表等内容，见 [PLAN.md](./PLAN.md)

---

*文档版本：v4.0（升级为原始位图传输）*
*最后更新：2026年6月*
*作者：AI 项目助手*
