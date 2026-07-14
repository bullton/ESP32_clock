# clock.py - 墨水屏时钟（服务端渲染模式）
# 架构：每分钟请求 /api/screen → 服务器用自己时间渲染 → ESP32 直接刷屏
# ESP32 无时间概念，只检测 X-Minute header 跨小时来触发全刷
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

FULL_REFRESH_INTERVAL = 3600    # 距离上次全刷超过此秒数则全刷
FETCH_INTERVAL        = 55      # 每次 fetch 间隔（秒），略短于 60s 留出处理时间

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

# ========== 拉取屏幕内容 ==========
def fetch_screen():
    """从服务器获取当前分钟的屏幕内容。"""
    try:
        env_temp = read_ds18b20_temp(ds18_sensor, ds18_roms)
        if env_temp is None:
            env_temp = 25.0
        url = SERVER_URL + "?env_temp=%.1f" % env_temp
        r = urequests.get(url, timeout=15)
        buf = r.content
        minute = int(r.headers.get("X-Minute", "-1"))
        r.close()
        if len(buf) != BUF_SIZE:
            print("长度 %d != %d" % (len(buf), BUF_SIZE))
            return None, -1
        return buf, minute
    except Exception as e:
        print("拉取失败: %s" % e)
        return None, -1

# ========== 刷屏 ==========
def display_screen(epd, buf, force_full=False):
    if force_full:
        epd.display_frame(buf)
    else:
        epd.partial_display(buf, 0, 0, WIDTH, HEIGHT)

# ========== 主循环 ==========
ds18_sensor = None
ds18_roms = []

def main():
    global ds18_sensor, ds18_roms
    print("=== 墨水屏时钟（每分钟请求服务器渲染）===")
    if not connect_wifi():
        print("WiFi 连接失败")
        return

    epd = init_epd()
    ds18_sensor, ds18_roms = init_ds18b20()

    last_full = 0
    last_minute = -1

    while True:
        buf, minute = fetch_screen()
        if buf is None:
            time.sleep(5)
            continue

        # 检测整点跨越：上一分钟是 59，当前是 0
        is_hourly = (last_minute == 59 and minute == 0)
        last_minute = minute

        # 判断是否需要全刷
        force_full = is_hourly or (time.time() - last_full) > FULL_REFRESH_INTERVAL

        display_screen(epd, buf, force_full=force_full)
        if force_full:
            last_full = time.time()
            print("[全刷] minute=%d" % minute)
        else:
            print("[局刷] minute=%d" % minute)

        # 等待下次 fetch
        time.sleep(FETCH_INTERVAL)

if __name__ == '__main__':
    main()
