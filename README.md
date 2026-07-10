# Clock - E-Ink Weather Clock

ESP32 墨水屏天气时钟，Python Flask 服务端渲染 → 15000 字节 raw bitmap → ESP32 直接刷屏。

## 架构

```
┌─────────────┐  HTTP GET   ┌────────────────┐
│   ESP32     │ ──────────► │   Flask Server │
│ 4.2" V2 屏  │ ◄────────── │  (Raspberry Pi)│
└─────────────┘  15000 bytes └────────────────┘
                       │
                       ▼
              ┌────────────────┐
              │ HKO 天气 API   │
              │ Google 翻译    │
              │ 港府假期表     │
              └────────────────┘
```

### 显示内容（400×300 1-bit）
1. 顶部栏：日期 · 公众假期 · 星期 · 城市 + WiFi
2. 主区：左 12:34 大时间 + 右实时/体感温度 + 风力/湿度
3. 中区：未来 7 日天气预报
4. 底部：自定义内容 / HKO 警告信息 / 港府新闻（按分钟轮换）

## 项目结构

```
.
├── clock.py            # ESP32 MicroPython 主程序
├── epaper4in2_V2.py    # 4.2" V2 墨水屏驱动
├── deploy.md           # 部署文档（SSH、NTP 等）
├── AGENTS.md           # 项目规则与坑点
├── .gitignore
└── server/             # 服务端
    ├── app.py          # Flask 入口
    ├── data.py         # 数据采集（HKO 天气、假期、警告）
    ├── renderer.py     # 1x / 2x 渲染器（PIL）
    ├── templates/
    │   └── admin.html  # 后台管理界面
    └── bottom_content.txt  # 用户自定义底部文本
```

## API 端点

| 路径 | 说明 |
|---|---|
| `GET /api/screen` | 1x 渲染 → 15000 字节 raw binary |
| `GET /api/screen.png` | 1x PNG 预览（浏览器） |
| `GET /api/screen_2x` | 2x 超采样渲染后缩放到 1x binary（15000 字节） |
| `GET /api/screen_2x.png` | 2x PNG 预览 |
| `GET /api/info` | 当前渲染数据 JSON |
| `GET /api/time` | 当前时间（ESP32 NTP 失败的 fallback） |
| `GET /admin` | 后台管理（修改底部内容等） |

### 查询参数
所有 endpoint 都支持：
- `?env_temp=25.5` - ESP32 现场温度（DS18B20）
- `?client_time=2026-06-24T22:30:00` - 用客户端时间替代服务端时间（避免 fetch+display 期间漂移）
- `?delay=5` - 服务端 sleep N 秒再返回（提前请求模式）

## ESP32 整点准时刷新方案

```
T=52  NTP 同步（消除累积漂移）
T=55  ESP32 发起 HTTP 请求（client_time=目标整点, delay=5）
T=55  服务端 sleep(5)
T=60  服务端渲染返回
T=60+ε ESP32 display
```

精度 < 1 秒（NTP + 网络延迟）。

## 服务端部署

```bash
cd server
pip install flask pillow requests
python3 app.py
# 默认监听 0.0.0.0:5000
```

## ESP32 烧录（MicroPython v1.28+）

```bash
# 用 Thonny 或 rshell 上传
- boot.py        # （可选）启动脚本
- clock.py       # 主程序
- epaper4in2_V2.py  # 屏幕驱动
- ds18x20.py, onewire.py  # 温度传感器驱动
```

GPIO：
- 屏幕：SCK=14, MOSI=42, CS=41, DC=2, RST=4, BUSY=5
- DS18B20：GPIO 35

## 数据源

- 实时天气 + 7 日预报：香港天文台（HKO）公开 JSON
- 天气警告：HKO 警告信息 API（15 分钟缓存）
- 公众假期：内置 2026/2027 香港假期表（`data.py:HK_HOLIDAYS`）

## 版本

- **v1.0** - 4 区布局（顶/主/中/底）、HKO 数据、自定义文本轮换、假期显示

## 许可

仅供个人使用。