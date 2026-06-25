# Clock Project - 关键规则

## 项目结构
- `server/` - Python Flask 服务端，部署在 `192.168.50.180:5000`
- `clock.py` - ESP32 端代码
- `deploy.md` - 部署文档（SSH 设置等）

## 渲染器布局规则（关键坑点）

### ⚠️ 两个渲染器都要改
`server/renderer.py` 有**两个**渲染器类：

- `Renderer2x` (class 在 line 275) - 高分辨率渲染（800x600）
- `Renderer` (class 在 line 484) - 1x 渲染（400x300）

**两个类的 `_draw_current_weather` 方法都要分别修改**，改了 1x 忘了 2x 会出现"改了不生效"的诡异问题。

### 字体 glyph bbox 偏移
字体 glyph 顶部相对 baseline 有偏移，必须用 `bbox_top` 修正：

```python
l, bbox_top, r, b = ImageDraw.Draw(Image.new("1", (1, 1))).textbbox((0, 0), "温", font=f_small)
row1_y = zone_top + margin - bbox_top  # 不是 zone_top + margin
```

**不能用 `zone_top + margin`**，否则 margin=N 实际视觉上是 N+bbox_top px。

实测值：
- 16px 字体（1x）：bbox_top = 5
- 32px 字体（2x）：bbox_top = 11

### 当前 margin/gap 值
- **1x** (400x300): margin=8, row_gap=8
- **2x** (800x600): margin=16, row_gap=16

## 布局常量

### 1x Layout
- `MAIN_TOP = 36`, `MAIN_BOTTOM = 115`（区域高 79px）
- `WEATHER_X1 = 204`, `M = 8`
- `DIV1_Y = 32`（MAIN_TOP 在分割线下方 4px）

### 2x Layout
- `MAIN_TOP = 72`, `MAIN_BOTTOM = 230`（区域高 158px）
- `WEATHER_X1 = 408`, `M = 16`

## 环境温度 (env_temp) 数据流

**坑点**：`app.py` 设 `data.ENV_TEMP` 但 `data.py` 用全局变量 `ENV_TEMP`，两者不是同一个！

修复方法：在 `data.py` 的 `current_weather()` 函数内：
```python
def current_weather():
    import data as _data_module  # 别用 "data"，会被 r.json() 遮蔽
    ...
    "env_temp": _data_module.ENV_TEMP,
```

## 部署命令

```bash
# 上传文件
scp -i ~/.ssh/id_rsa_bullton_180_nopass <local_file> bullton@192.168.50.180:/home/bullton/clock_server/

# 重启服务（注意 nohup 后台运行）
ssh -i ~/.ssh/id_rsa_bullton_180_nopass bullton@192.168.50.180 "pkill -f 'python3 app.py'; sleep 1; cd /home/bullton/clock_server && rm -rf __pycache__ && nohup python3 app.py > server.log 2>&1 &"

# 测试
curl.exe -s "http://192.168.50.180:5000/api/screen.png?env_temp=25.5" -w "%{http_code}"
curl.exe -s "http://192.168.50.180:5000/api/screen_2x" -o test.bin  # 应为 15000 字节
```

## API 端点

- `/api/screen` - 1x binary (15000 bytes)
- `/api/screen.png` - 1x PNG 预览
- `/api/screen_2x` - 2x 超采样渲染后缩小到 1x binary (15000 bytes)
- `/api/screen_2x.png` - 2x PNG 预览

查询参数（所有 endpoint 都支持）：
- `?env_temp=25.5` - 设置环境温度
- `?client_time=2026-06-24T22:30:00` - 用客户端时间替代服务端时间渲染
- `?delay=5` - 服务端 sleep N 秒后再渲染返回（提前请求模式）

## ESP32 整点准时刷新方案（clock.py）

**问题**：ESP32 内部 RTC 用 8MHz RC 振荡器，每分钟漂移 0.3-1 秒，1 小时累积 12 秒。

**方案**：客户端提前请求 + 服务端 sleep 等到整点

时间线：
```
T=52  ESP32 NTP 校准（消除累积漂移）
T=55  ESP32 发起 HTTP 请求（client_time=目标整点, delay=5）
T=55  服务端 sleep(5)
T=60  服务端 sleep 完，渲染（用 client_time），返回
T=60+ε ESP32 收到，立刻 display
```

**精度**：< 1 秒（NTP + 网络延迟）

**关键常量**（clock.py 顶部）：
```python
NTP_HOST        = "stdtime.gov.hk"   # 香港天文台 NTP 源（IPv4）
NTP_SYNC_BEFORE = 8   # 整点前 8 秒 NTP 同步
FETCH_BEFORE    = 5   # 整点前 5 秒发起请求
```

**ESP32 端超时**：fetch timeout=15 秒（> delay + 渲染时间）

## 调试技巧

调试 margin/gap 时，用临时脚本 trace `draw.text` 调用，看 xy 参数：
```python
from PIL import ImageDraw
original = ImageDraw.ImageDraw.text
def patched(self, xy, text, **kw):
    print(f'xy={xy}, text={text!r}')
    return original(self, xy, text, **kw)
ImageDraw.ImageDraw.text = patched
```
