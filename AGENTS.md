# Clock Project - 关键规则

## 项目结构
- `server/` - Python Flask 服务端，部署在 `192.168.50.180:5000`
- `clock.py` - ESP32 端代码
- `deploy.md` - 部署文档（SSH 设置等）

## 渲染器布局规则（关键坑点）

### ⚠️ 两个渲染器都要改
`server/renderer.py` 有**两个**渲染器类：

- `Renderer2x`（搜索 `class Renderer2x`）- 高分辨率渲染（800x600）
- `Renderer`（搜索 `class Renderer`）- 1x 渲染（400x300）

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

### 顶部栏（_draw_top_bar）
- 日期在左（`self.L.M + 8`），周几居中，城市+WiFi 在右
- 当天是公众假期时，日期后用 **tiny 字体**（1x=10px, 2x=20px）显示假期名
- 假期数据在 `data.py` 的 `HK_HOLIDAYS`（2026/2027）

### 底部文本框边距（_draw_bottom_text）
- 左右固定 **16px**（写死，远离 1x 边框 x=8 和 2x 边框 x=0）
- 上下 **+4 / -4** 在 BOTTOM_TOP / BOTTOM_BOT 内
- `max_width = self.L.W - 32`（16 左边 + 16 右边，左右边距相同）
- **不自动换行**：无 `\n` 时单行显示（段落不超过 max_width）
- **超宽按字符切**：段落超过 max_width 时按字符贪心断行
- **超行截断**：超出 max_lines 时末尾加 `…`

## 字体方案（2026-11 新增，可在后台切换）

文字渲染由两层决定：`styles.py` 里的方案（字重 + 栅格化方式），以及 `renderer.py` 里的
`MonoTextRenderer`（FreeType 字模 + 可选超采样阈值）。

- 方案列表在 `server/styles.py` 的 `PROFILES`，切换结果存 `server/style.json`（已 gitignore）。
- `aa = -1` → 走 PIL 原生 `draw.text`（即旧版效果，`classic`）；`aa = 0` → FreeType 单色栅格化；
  `aa > 1` → 按 N 倍字号灰度渲染、缩回后按阈值二值化（阈值越小笔画越粗）。
- 栅格化参数通过 `contextvars`（`_RASTER`）传入被 monkey-patch 的 `ImageDraw.text`，
  渲染期间由 `Renderer.render()` 设置，见 `set_raster()/reset_raster()`。
- ⚠️ 旧代码用 `draw.im` 直接 `putpixel/paste`，Pillow 9+ 下 `self.im` 是 `ImagingCore` 没有这些方法，
  异常被 `except: pass` 吞掉 → 每次都静默回退到 PIL 渲染。现在统一用 `self._image`。
- ⚠️ FreeType 单色位图每行按 `bitmap.pitch` 补齐（不一定等于 `(w+7)//8`），解包时必须按 pitch 跳行。
- 后台入口：`/console#screen` 的「字体方案」卡片，接口 `GET/POST /api/console/styles`、
  `GET /api/console/style_preview?profile=`。

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
# 推荐流程：先 push 到 origin/master，再在服务器上拉取并执行 deploy.sh
git push origin master
ssh -i ~/.ssh/id_rsa_bullton_180_nopass bullton@192.168.50.180 "cd /home/bullton/clock_server && git pull --ff-only origin master && bash deploy.sh"

# 单独上传单个文件
scp -i ~/.ssh/id_rsa_bullton_180_nopass <local_file> bullton@192.168.50.180:/home/bullton/clock_server/server/

# 测试
curl.exe -s "http://192.168.50.180:5000/api/screen.png?env_temp=25.5" -w "%{http_code}"
curl.exe -s "http://192.168.50.180:5000/api/screen_2x" -o test.bin  # 应为 15000 字节
```

**重要**：服务由 **PM2** 托管（`pm2 list` 里的 `clock_server`，cwd `/home/bullton/clock_server`，`python3 app.py`）。
**不要** `pkill -f 'python3 app.py'`——进程被杀后 PM2 会立刻拉起新实例，和手动 `nohup` 启动的实例抢 5000 端口，
日志里会出现 `Address already in use`。重启请用 `pm2 restart clock_server`（`deploy.sh` 已内置）。
PM2 日志在 `~/.pm2/logs/clock-server-{out,error}.log`，`server.log` 只是历史遗留。

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
NTP_HOST        = "0.hk.pool.ntp.org"   # 香港 NTP 池（更可靠）
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

## 后台与权限（2026-11 重构）

### 入口
- GET /console —— 统一后台（概览 / 画面 / 内容 / 系统 / 账号）
- GET /admin → 重定向 /console#content；GET /preview → /console#screen
- GET /login —— 单密码登录；/logout 退出

### 密码
- 密码哈希与 session 密钥保存在 server/auth.json（已加入 .gitignore）
- 首次启动自动生成，默认密码 clock2026，会打印到启动日志，登录后请到「账号」页修改
- 设置环境变量 CLOCK_ADMIN_PASSWORD 可接管密码，此时界面修改密码会被禁用
- 忘记密码：删除 server/auth.json 后重启，会重新生成

### 受保护 / 公开
- 需登录：/console、/api/info、/api/bottom_content、/api/debug/layout、
  /api/console/*、/api/account*
- 保持公开（设备与预览用）：/api/screen、/api/screen_2x、/api/screen.png、
  /api/screen_2x.png、/api/screen_raw.png、/api/time、/api/health

### 前端资源
- 模板：server/templates/console.html、login.html
- 样式：server/static/css/console.css（设计令牌集中在 :root）
- 脚本：server/static/js/console.js
- 字体：server/static/fonts/Unbounded-Medium.ttf

### 底栏符号与表情
- 面板数据在 server/symbols.py（SYMBOL_GROUPS 内容 + EMOJI_MAP 降级表）
- 渲染时 enderer.prepare_bottom_text() 处理：有表情字体则保留 emoji，
  否则按降级表替换；无法识别的 emoji 变成 ·
- 想启用真实 emoji：把单色 outline 字体放进 server/fonts/ 后重启