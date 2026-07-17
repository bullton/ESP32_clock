# clock.py - 墨水屏时钟（服务端渲染模式）
# 架构：服务端返回 15000 字节 MONO_HLSB 位图 → ESP32 直接刷屏
# 服务器返回什么时间就显示什么时间，ESP32 不做任何时间同步
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

WIDTH  = 400
HEIGHT = 300
BUF_SIZE = WIDTH * HEIGHT // 8

FULL_REFRESH_INTERVAL = 3600

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
    print("=== 墨水屏时钟 ===")
    if not connect_wifi():
        print("WiFi 连接失败")
        return

    epd = init_epd()
    ds18_sensor, ds18_roms = init_ds18b20()

    last_full = 0
    next_interval = 50
    buf = None

    while True:
        print("[等待] %.1fs 后请求..." % next_interval)
        sleep_sec(next_interval)

        buf, next_interval = fetch_bitmap()
        if buf is None:
            next_interval = 10
            continue

        display(epd, buf, force_full=False)
        if (time.time() - last_full) > FULL_REFRESH_INTERVAL:
            epd.init()
            epd.display_frame(buf)
            last_full = time.time()
            print("[全刷] 完成")

if __name__ == '__main__':
    main()