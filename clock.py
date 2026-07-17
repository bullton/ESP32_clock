# clock.py - 墨水屏时钟（服务端整点同步模式）
# 架构：服务端等待到整点返回，X-Next-Request-In 告知下次请求秒数
# ESP32 只管 sleep 那个秒数，无需校准
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
SERVER_URL    = "http://192.168.50.180:5000/api/screen"
NTP_HOST      = "stdtime.gov.hk"
TZ_OFFSET_SEC = 8 * 3600

WIDTH  = 400
HEIGHT = 300
BUF_SIZE = WIDTH * HEIGHT // 8

FULL_REFRESH_INTERVAL = 3600
NTP_SYNC_INTERVAL    = 300
INITIAL_WAIT        = 50

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
    try:
        pin = Pin(DS18B20_PIN, Pin.IN, Pin.PULL_UP)
        ow = OneWire(pin)
        sensor = ds18x20.DS18X20(ow)
        roms = sensor.scan()
        if not roms:
            print("[DS18B20] 未检测到设备")
            return None, []
        print("[DS18B20] 找到 %d 个设备" % len(roms))
        return sensor, roms
    except Exception as e:
        print("[DS18B20] 初始化失败: %s" % e)
        return None, []

def read_ds18b20_temp(sensor, roms):
    if sensor is None or not roms:
        return None
    try:
        temp = sensor.temp_js(roms[0])
        if temp is not None:
            print("[DS18B20] 温度: %.1f C" % temp)
        return temp
    except Exception as e:
        print("[DS18B20] 读取异常: %s" % e)
        return None

# ========== NTP 时间同步 ==========
def sync_ntp():
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

# ========== 拉取位图 ==========
def fetch_bitmap():
    try:
        env_temp = read_ds18b20_temp(ds18_sensor, ds18_roms)
        if env_temp is None:
            env_temp = 25.0
        url = SERVER_URL + "?env_temp=%.1f" % env_temp
        r = urequests.get(url, timeout=15)
        buf = r.content
        next_interval = int(r.headers.get("X-Next-Request-In", "50"))
        r.close()
        if len(buf) != BUF_SIZE:
            print("长度 %d != %d" % (len(buf), BUF_SIZE))
            return None, None
        return buf, next_interval
    except Exception as e:
        print("拉取失败: %s" % e)
        return None, None

# ========== 刷屏 ==========
def display(epd, buf, force_full=False):
    if force_full:
        epd.init()
        epd.display_frame(buf)
    else:
        epd.partial_display(buf, 0, 0, WIDTH, HEIGHT)

# ========== 精确 sleep ==========
def sleep_sec(s):
    while s > 0:
        if s > 1:
            time.sleep(s - 0.1)
            s = 0.1
        else:
            time.sleep(s)
            s = 0

# ========== 主循环 ==========
ds18_sensor = None
ds18_roms = []

def main():
    global ds18_sensor, ds18_roms
    print("=== 墨水屏时钟（服务端整点同步）===")
    if not connect_wifi():
        print("WiFi 连接失败")
        return

    epd = init_epd()
    sync_ntp()

    ds18_sensor, ds18_roms = init_ds18b20()

    last_full = 0
    last_ntp = 0
    next_interval = INITIAL_WAIT
    buf = None

    while True:
        now = time.time()
        if now - last_ntp > NTP_SYNC_INTERVAL:
            if sync_ntp():
                last_ntp = now

        print("[等待] %.1fs 后请求..." % next_interval)
        sleep_sec(next_interval)

        buf, next_interval = fetch_bitmap()
        if buf is None:
            next_interval = 10
            continue

        local = time.localtime(time.time() + TZ_OFFSET_SEC)
        is_hourly = (local[4] == 0)
        force_full = is_hourly or (time.time() - last_full) > FULL_REFRESH_INTERVAL
        display(epd, buf, force_full=force_full)
        if force_full:
            last_full = time.time()
            print("[全刷] 完成")

if __name__ == '__main__':
    main()