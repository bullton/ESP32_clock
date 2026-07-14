# epaper4in2_V2.py - 4.2寸墨水屏 V2 版本驱动
# 基于官方 EPD_4IN2_V2.cpp 移植

from micropython import const
from time import sleep_ms
import ustruct

# Display resolution
EPD_WIDTH  = const(400)
EPD_HEIGHT = const(300)

# Display commands
POWER_SETTING      = const(0x01)
POWER_ON          = const(0x04)
POWER_OFF          = const(0x02)
DEEP_SLEEP        = const(0x07)
PANEL_SETTING     = const(0x00)
VCOM_AND_DATA_INTERVAL = const(0x50)
TCON_SETTING      = const(0x60)
RESOLUTION_SETTING = const(0x61)
DISPLAY_REFRESH   = const(0x12)

# V2版本: BUSY=1 表示忙, BUSY=0 表示空闲
BUSY = const(1)

class EPD:
    def __init__(self, spi, cs, dc, rst, busy):
        self.spi = spi
        self.cs = cs
        self.dc = dc
        self.rst = rst
        self.busy = busy
        self.cs.init(self.cs.OUT, value=1)
        self.dc.init(self.dc.OUT, value=0)
        self.rst.init(self.rst.OUT, value=1)
        self.busy.init(self.busy.IN)
        self.width = EPD_WIDTH
        self.height = EPD_HEIGHT

    def _command(self, command, data=None):
        self.dc(0)
        self.cs(0)
        self.spi.write(bytearray([command]))
        self.cs(1)
        if data is not None:
            self._data(data)

    def _data(self, data):
        self.dc(1)
        self.cs(0)
        self.spi.write(data)
        self.cs(1)

    def _read_busy(self):
        # V2: BUSY=1 时等待
        while self.busy.value() == BUSY:
            sleep_ms(10)

    def reset(self):
        # 官方时序: 高 -> 拉低(2ms) -> 高
        self.rst(1)
        sleep_ms(100)
        self.rst(0)
        sleep_ms(2)
        self.rst(1)
        sleep_ms(100)

    def init(self):
        self.reset()
        self._read_busy()

        # 软复位
        self._command(0x12)
        self._read_busy()

        # 显示更新控制
        self._command(0x21)
        self._data(bytearray([0x40, 0x00]))

        # 边框波形
        self._command(0x3C)
        self._data(bytearray([0x05]))

        # 数据入口模式 - X-mode
        self._command(0x11)
        self._data(bytearray([0x03]))

        # 设置窗口
        self._set_windows(0, 0, EPD_WIDTH - 1, EPD_HEIGHT - 1)
        self._set_cursor(0, 0)

        self._read_busy()

    def _set_windows(self, x_start, y_start, x_end, y_end):
        self._command(0x44)
        self._data(bytearray([(x_start >> 3) & 0xFF, (x_end >> 3) & 0xFF]))
        self._command(0x45)
        self._data(bytearray([y_start & 0xFF, (y_start >> 8) & 0xFF,
                              y_end & 0xFF, (y_end >> 8) & 0xFF]))

    def _set_cursor(self, x, y):
        self._command(0x4E)
        self._data(bytearray([x & 0xFF]))
        self._command(0x4F)
        self._data(bytearray([y & 0xFF, (y >> 8) & 0xFF]))

    def _turn_on_display(self):
        self._command(0x22)
        self._data(bytearray([0xF7]))
        self._command(0x20)
        self._read_busy()

    def _turn_on_display_partial(self):
        # 局刷: 0x22 + 0xFF
        self._command(0x22)
        self._data(bytearray([0xFF]))
        self._command(0x20)
        self._read_busy()

    def partial_display(self, frame_buffer, x_start, y_start, x_end, y_end):
        """局刷：在指定区域内刷新图像
        frame_buffer: 图像数据，宽度=((x_end-x_start)//8), 高度=(y_end-y_start)
        x_start, y_start: 起始像素坐标
        x_end, y_end: 结束像素坐标
        """
        # X坐标对齐处理（参考官方代码）
        if (x_start % 8 + x_end % 8 == 8 and x_start % 8 > x_end % 8) or \
           x_start % 8 + x_end % 8 == 0 or (x_end - x_start) % 8 == 0:
            x_start = x_start // 8
            x_end = x_end // 8
        else:
            x_start = x_start // 8
            x_end = x_end // 8 + 1 if x_end % 8 != 0 else x_end // 8

        # 转换后: x_start, x_end 是字节索引
        width = x_end - x_start
        image_counter = width * (y_end - y_start)

        # 官方代码: Xend -= 1, Yend -= 1
        x_end -= 1
        y_end -= 1

        # 边框波形
        self._command(0x3C)
        self._data(bytearray([0x80]))

        # 显示更新控制
        self._command(0x21)
        self._data(bytearray([0x00, 0x00]))

        self._command(0x3C)
        self._data(bytearray([0x80]))

        # 设置窗口 - 用字节索引
        self._command(0x44)
        self._data(bytearray([x_start & 0xFF, x_end & 0xFF]))
        self._command(0x45)
        self._data(bytearray([y_start & 0xFF, (y_start >> 8) & 0x01,
                              y_end & 0xFF, (y_end >> 8) & 0x01]))

        # 设置光标
        self._command(0x4E)
        self._data(bytearray([x_start & 0xFF]))
        self._command(0x4F)
        self._data(bytearray([y_start & 0xFF, (y_start >> 8) & 0x01]))

        # 发送数据
        self._command(0x24)
        for i in range(image_counter):
            self._data(bytearray([frame_buffer[i]]))

        self._turn_on_display_partial()

    def display_frame(self, frame_buffer):
        if frame_buffer is None:
            return

        width = (EPD_WIDTH // 8)
        height = EPD_HEIGHT

        # 切回 full refresh 模式（覆盖 partial 残留的 0x3C/0x21 寄存器状态）
        # 否则 partial 模式下触发的全刷不会彻底清 ghost
        self._command(0x21)
        self._data(bytearray([0x40, 0x00]))
        self._command(0x3C)
        self._data(bytearray([0x05]))

        # 发送数据到 black RAM (0x24)
        self._command(0x24)
        for j in range(height):
            for i in range(width):
                self._data(bytearray([frame_buffer[i + j * width]]))

        # 发送数据到 red RAM (0x26) - V2需要发两遍
        self._command(0x26)
        for j in range(height):
            for i in range(width):
                self._data(bytearray([frame_buffer[i + j * width]]))

        self._turn_on_display()

    def clear(self):
        width = (EPD_WIDTH // 8)
        height = EPD_HEIGHT

        self._command(0x24)
        for j in range(height):
            for i in range(width):
                self._data(bytearray([0xFF]))

        self._command(0x26)
        for j in range(height):
            for i in range(width):
                self._data(bytearray([0xFF]))

        self._turn_on_display()

    def sleep(self):
        self._command(0x10)
        self._data(bytearray([0x01]))
        sleep_ms(200)
