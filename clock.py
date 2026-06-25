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
import ntptime
from machine import Pin, SPI
import epaper4in2_V2
from onewire import OneWire
import ds18x20

# ========== 配置 ==========
WIFI_SSID     = "NETGEAR_28A"
WIFI_PASSWORD = "18005711470"
SERVER_URL    = "http://192.168.50.180:5000/api/screen_2x"
NTP_HOST      = "stdtime.gov.hk"
TZ_OFFSET_SEC = 8 * 3600

WIDTH  = 400
HEIGHT = 300
BUF_SIZE = WIDTH * HEIGHT // 8

FULL_REFRESH_INTERVAL = 3600
NTP_SYNC_BEFORE      = 7              # 整点前 7 秒 NTP 同步
FETCH_LEAD           = 5              # 整点前 5 秒 fetch，让服务端 sleep 5 秒到整点返回
DISPLAY_BEFORE       = 0.3            # display 启动在整点前 0.3 秒

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

# ========== NTP 时间同步 ==========
def sync_ntp():
    """同步 RTC 到本地时间（UTC+8）。"""
    try:
        ntptime.host = NTP_HOST
        ntptime.settime()
        t = time.localtime(time.time() + TZ_OFFSET_SEC)
        print("[NTP] %04d-%02d-%02d %02d:%02d:%02d" %
              (t[0], t[1], t[2], t[3], t[4], t[5]))
        return True
    except Exception as e:
        print("[NTP] 失败: %s" % e)
        return False

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
    print("=== 墨水屏时钟（提前 fetch + 整点 display）===")
    if not connect_wifi():
        print("WiFi 连接失败")
        return

    epd = init_epd()
    sync_ntp()

    ds18_sensor, ds18_roms = init_ds18b20()

    last_full = 0
    target_ticks = 0

    while True:
        # ===== 计算下次刷屏目标时刻（整点） =====
        now = time.time()
        if target_ticks == 0:
            # 首次：必须先确保 RTC 准确（启动时 NTP 可能失败）
            # 检查方法：年 > 2024 才算校准（避免 boot_time 算错）
            local_check = time.localtime(now)
            if local_check[0] < 2024:
                print("[RTC 未校准] 当前 RTC=%d sec, year=%d" % (now, local_check[0]))
                print("[RTC 未校准] 等待 NTP 同步...")
                for _ in range(60):  # 最多等 60 秒
                    time.sleep(2)
                    if sync_ntp():
                        now = time.time()
                        local_check = time.localtime(now)
                        if local_check[0] >= 2024:
                            break

            local = time.localtime(now + TZ_OFFSET_SEC)
            wait_sec = 60 - local[5]
            if local[5] == 0:
                wait_sec = 0
            target_ticks = now + wait_sec
            print("[首次] 对齐整点 %s，等待 %.1fs" %
                  (local_time_str(target_ticks), wait_sec))
        else:
            target_ticks += 60

        # ===== 整点前 NTP 同步 =====
        if target_ticks - now >= NTP_SYNC_BEFORE + 1:
            sleep_until(target_ticks - NTP_SYNC_BEFORE)
            if not sync_ntp():
                print("[警告] NTP 同步失败，本次跳过整点")
                continue
            print("[NTP 校准] 当前 RTC = %s" % local_time_str(time.time()))

        # ===== 提前 fetch（让服务端 sleep 到整点返回） =====
        # 整点前 FETCH_LEAD 秒发起请求
        fetch_at = target_ticks - FETCH_LEAD
        now = time.time()
        if fetch_at - now > 0:
            sleep_until(fetch_at)

        # 客户端时间 = 目标整点对应的本地时间
        target_client_time = local_time_str(target_ticks)
        # 服务端 sleep 时间 = fetch 启动到整点
        delay = max(0.5, target_ticks - time.time())

        print("[fetch] client=%s delay=%.1fs target=%s" %
              (target_client_time, delay, local_time_str(target_ticks)))
        buf = fetch_bitmap(target_client_time, delay)
        if buf is None:
            print("拉取失败，保持上一帧")
            continue

        # ===== 缓存 buf，sleep 到整点前 DISPLAY_BEFORE 秒再 display =====
        # 此时 RTC 已经接近整点（fetch 耗时让 fetch 完成在 ~整点）
        display_at = target_ticks - DISPLAY_BEFORE
        now = time.time()
        if display_at - now > 0:
            sleep_until(display_at)

        # ===== display =====
        force_full = (target_ticks - last_full) > FULL_REFRESH_INTERVAL
        display(epd, buf, force_full=force_full)
        actual = time.time()
        drift = actual - target_ticks  # display 完成相对整点的偏差
        if force_full:
            last_full = target_ticks
            print("[全刷] 偏差 %.2fs" % drift)
        else:
            print("[局刷] 偏差 %.2fs" % drift)

if __name__ == '__main__':
    main()
