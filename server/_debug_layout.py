"""Render debug image with zone labels"""
import sys
sys.path.insert(0, 'D:/Code/Clock/server')
from PIL import Image, ImageDraw
import renderer, data

fonts = renderer.load_fonts()
L = renderer.Layout

# Current layout values
print('Current Layout (SCALE=%d):' % L.SCALE)
attrs = [a for a in dir(L) if a.isupper() and not a.startswith('_')]
for a in sorted(attrs):
    print('  %s = %d' % (a, getattr(L, a)))

print()

# Test with generous spacing zones (manually tuned)
zones_new = {
    'TOP_Y':    12,
    'DIV1_Y':   50,
    'TIME_Y':    100,   # baseline
    'DIV2_Y':   340,
    'WEATHER_Y': 348,
    'DIV3_Y':   440,
    'FCST_Y':    448,
    'DIV4_Y':   528,
    'POEM_Y':    534,
    'DIV5_Y':   580,
    'FOOT_Y':    584,
}

print('New proposed zones:')
for k, v in zones_new.items():
    print('  %s = %d' % (k, v))

print()
print('Zone heights:')
print('  TIME zone: %d px (from %d to %d)' % (zones_new['DIV2_Y'] - zones_new['TIME_Y'],
    zones_new['TIME_Y'], zones_new['DIV2_Y']))
print('  WEATHER zone: %d px' % (zones_new['DIV3_Y'] - zones_new['WEATHER_Y']))
print('  FCST zone: %d px' % (zones_new['DIV4_Y'] - zones_new['FCST_Y']))
print('  POEM zone: %d px' % (zones_new['DIV5_Y'] - zones_new['POEM_Y']))
print('  FOOT zone: %d px' % (600 - zones_new['FOOT_Y']))
print()
print('Total: last zone bottom = %d, canvas = 600' % (zones_new['FOOT_Y'] + 30))
