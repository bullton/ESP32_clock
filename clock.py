# clock.py - 墨水屏时钟（服务端 raw buffer 模式）
# 架构：服务端返回 15000 字节 MONO_HLSB 位图 → ESP32 直接刷屏
# 时间同步：提前 fetch + sleep 到整点前再 display，最大化整点精度
#
# 时间线：
#   T=52  NTP 同步（消除 RTC 漂移）
#   T=53  fetch 启动（client_time=目标整点, delay=5）
#   T=58  服务端 sleep 完，渲染返回
#   T=58  ESP32 收到 buf，缓存
#   T=59.5 sleep_until 唤醒
#   T=59.5 display 启动（partial_display ~1s）
#   T=60.5 display 完成（误差 < 1s）
#
# GPIO（ESP32-S3）：
#   SCK=14, MOSI=42, CS=41, DC=2, RST=4, BUSY=5

import network
import urequests
import time
from machine import Pin, SPI
import epaper4in2_V2
from onewire import OneWire
import ds18x20

# ========== 配置 ==========
WIFI_SSID     = "NETGEAR_28A"
WIFI_PASSWORD = "18005711470"
SERVER_URL    = "http://192.168.50.180:5000/api/screen"
SERVER_TIME_URL = "http://192.168.50.180:5000/api/time"
TZ_OFFSET_SEC = 8 * 3600

WIDTH  = 400
HEIGHT = 300
BUF_SIZE = WIDTH * HEIGHT // 8

FULL_REFRESH_INTERVAL = 3600
FETCH_LEAD           = 5              # 整点前 5 秒 fetch，让服务端 sleep 5 秒到整点返回
DISPLAY_BEFORE       = 0.3            # display 启动在整点前 0.3 秒
HOURLY_FULL_REFRESH  = True          # 整点时强制全刷（避免 partial 残留像素）

# ========== 硬件初始化 ==========
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

# ========== WiFi ==========
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        for _ in range(20):
            if wlan.isconnected():
                return True
            time.sleep(1)
    return wlan.isconnected()

# ========== DS18B20 温度传感器 ==========
DS18B20_PIN = 35

def init_ds18b20():
    """初始化 DS18B20，返回 sensor 对象和rom列表。"""
    try:
        pin = Pin(DS18B20_PIN, Pin.IN, Pin.PULL_UP)
        ow = OneWire(pin)
        sensor = ds18x20.DS18X20(ow)
        roms = sensor.scan()
        if not roms:
            print("[DS18B20] 未检测到设备，请检查接线")
            return None, []
        print("[DS18B20] 找到 %d 个设备" % len(roms))
        for rom in roms:
            print("[DS18B20] ROM: %s" % ''.join('%02x' % b for b in rom))
        return sensor, roms
    except Exception as e:
        print("[DS18B20] 初始化失败: %s" % e)
        return None, []

def read_ds18b20_temp(sensor, roms):
    """读取 DS18B20 温度，返回浮点数。失败返回 None。"""
    if sensor is None or not roms:
        return None
    try:
        temp = sensor.temp_js(roms[0])
        if temp is not None:
            print("[DS18B20] 温度: %.1f C" % temp)
        else:
            print("[DS18B20] 读取失败")
        return temp
    except Exception as e:
        print("[DS18B20] 读取异常: %s" % e)
        return None

# ========== 服务器时间同步 ==========
def fetch_server_time():
    """从服务器 /api/time 获取当前 Unix 时间戳（UTC+8）。"""
    try:
        r = urequests.get(SERVER_TIME_URL, timeout=10)
        import ujson
        d = ujson.loads(r.content)
        r.close()
        ts = d["ts"]
        t = time.localtime(ts + TZ_OFFSET_SEC)
        print("[时间] %04d-%02d-%02d %02d:%02d:%02d (from server)" %
              (t[0], t[1], t[2], t[3], t[4], t[5]))
        return ts
    except Exception as e:
        print("[时间] 获取失败: %s" % e)
        return None

# ========== 计算本地时间字符串 ==========
def local_time_str(ticks):
    t = time.localtime(ticks + TZ_OFFSET_SEC)
    return "%04d-%02d-%02dT%02d:%02d:%02d" % \
           (t[0], t[1], t[2], t[3], t[4], t[5])

# ========== 拉取 15000 字节位图 ==========
def fetch_bitmap(client_time, delay):
    """client_time: 目标显示时间。delay: 服务端 sleep 秒数。"""
    try:
        env_temp = read_ds18b20_temp(ds18_sensor, ds18_roms)
        if env_temp is None:
            env_temp = 25.0  # fallback
        url = SERVER_URL + "?env_temp=%.1f&client_time=%s&delay=%.2f" % \
              (env_temp, client_time, delay)
        r = urequests.get(url, timeout=15)
        buf = r.content
        r.close()
        if len(buf) != BUF_SIZE:
            print("长度 %d != %d" % (len(buf), BUF_SIZE))
            return None
        return buf
    except Exception as e:
        print("拉取失败: %s" % e)
        return None

# ========== 刷屏 ==========
def display(epd, buf, force_full=False):
    if force_full:
        epd.display_frame(buf)
    else:
        epd.partial_display(buf, 0, 0, WIDTH, HEIGHT)

# ========== 精确 sleep ==========
def sleep_until(target_ticks):
    """睡到 time.time() == target_ticks。"""
    while True:
        remain = target_ticks - time.time()
        if remain <= 0:
            return
        if remain > 0.5:
            time.sleep(remain - 0.2)
        elif remain > 0.02:
            time.sleep(remain / 2)
        else:
            time.sleep_ms(int(remain * 1000))

# ========== 主循环 ==========
ds18_sensor = None
ds18_roms = []

def main():
    global ds18_sensor, ds18_roms
    print("=== 墨水屏时钟（每分钟从服务器拿时间）===")
    if not connect_wifi():
        print("WiFi 连接失败")
        return

    epd = init_epd()

    # 启动时从服务器获取一次准确时间
    server_ts = fetch_server_time()
    if server_ts is None:
        print("[错误] 无法获取服务器时间，退出")
        return

    ds18_sensor, ds18_roms = init_ds18b20()

    last_full = 0
    target_ticks = 0

    while True:
        # ===== 每次都从服务器拿时间 =====
        server_ts = fetch_server_time()
        if server_ts is None:
            print("[警告] 服务器时间获取失败，5 秒后重试")
            time.sleep(5)
            continue

        # ===== 计算下次刷屏目标时刻（对齐整分） =====
        if target_ticks == 0:
            local = time.localtime(server_ts + TZ_OFFSET_SEC)
            wait_sec = 60 - local[5]
            if local[5] == 0:
                wait_sec = 0
            target_ticks = server_ts + wait_sec
            print("[首次] 对齐整分 %s，等待 %.1fs" %
                  (local_time_str(target_ticks), wait_sec))
        else:
            target_ticks += 60

        # ===== 判断是否整点 =====
        prev_min = time.localtime(target_ticks - 60 + TZ_OFFSET_SEC)[4]
        next_min = time.localtime(target_ticks + TZ_OFFSET_SEC)[4]
        is_hourly = (prev_min == 59 and next_min == 0)

        # ===== 提前 fetch（让服务端 sleep 到整点返回） =====
        fetch_at = target_ticks - FETCH_LEAD
        if fetch_at - server_ts > 0:
            sleep_until(fetch_at)
            # 再次确认时间（确保整点精确）
            server_ts = fetch_server_time()
            if server_ts is None:
                continue

        # 客户端时间 = 目标整点对应的本地时间
        target_client_time = local_time_str(target_ticks)
        # 服务端 sleep 时间
        delay = max(0.5, target_ticks - server_ts)

        print("[fetch] client=%s delay=%.1fs target=%s" %
              (target_client_time, delay, local_time_str(target_ticks)))
        buf = fetch_bitmap(target_client_time, delay)
        if buf is None:
            print("拉取失败，保持上一帧")
            continue

        # ===== display =====
        force_full = is_hourly or (target_ticks - last_full) > FULL_REFRESH_INTERVAL
        display(epd, buf, force_full=force_full)
        drift = server_ts - target_ticks
        if force_full:
            last_full = target_ticks
            print("[全刷] 偏差 %.2fs" % drift)
        else:
            print("[局刷] 偏差 %.2fs" % drift)

if __name__ == '__main__':
    main()
