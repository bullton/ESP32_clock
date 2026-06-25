# ds18x20.py - DS18B20/DS18S20 driver for MicroPython
# MIT license

from onewire import OneWireError


class DS18X20:
    CONVERT_TEMP = 0x44
    READ_SCRATCHPAD = 0xBE
    WRITE_SCRATCHPAD = 0x4E
    READ_POWER_SUPPLY = 0xB4
    SEARCH = 0xF0

    def __init__(self, onewire):
        self.ow = onewire
        self.buf = bytearray(9)

    def scan(self):
        return [rom for rom in self.ow.scan() if rom[0] == 0x10 or rom[0] == 0x28]

    def _convert_temp(self, rom):
        self.ow.reset()
        self.ow.select_rom(rom)
        self.ow.writebyte(self.CONVERT_TEMP)

    def _read_scratchpad(self, rom):
        self.ow.reset()
        self.ow.select_rom(rom)
        self.ow.writebyte(self.READ_SCRATCHPAD)
        for i in range(9):
            self.buf[i] = self.ow.readbyte()
        return self.buf

    def temp_js(self, rom):
        """Read temperature in Celsius. Returns None if reading fails."""
        if rom[0] == 0x10:
            return self._temp_ds18s20(rom)
        elif rom[0] == 0x28:
            return self._temp_ds18b20(rom)
        return None

    def _temp_ds18s20(self, rom):
        self._convert_temp(rom)
        import time
        time.sleep_ms(750)
        buf = self._read_scratchpad(rom)
        if self.ow.crc8(buf):
            return None
        t = (buf[1] << 8) | buf[0]
        if t == 0xFF:
            return None
        count = buf[7]
        if count > 0:
            t = ((t & 0xFFFE) << 1) - ((t & 1) << 1)
            t = t * 625 // (count * 100)
        else:
            t = t * 625 // 100
        return t / 100.0

    def _temp_ds18b20(self, rom):
        self._convert_temp(rom)
        import time
        time.sleep_ms(750)
        buf = self._read_scratchpad(rom)
        if self.ow.crc8(buf):
            return None
        t = (buf[1] << 8) | buf[0]
        if t == 0xFF:
            return None
        cfg = buf[4]
        if cfg & 0x60 == 0x60:
            bits = 12
        elif cfg & 0x40 == 0x40:
            bits = 11
        elif cfg & 0x20 == 0x20:
            bits = 10
        else:
            bits = 9
        if bits > 9:
            t = t & ~((1 << (bits - 9)) - 1)
        return t / 16.0
