import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import float2percent


FLOAT2PERCENT_CASES = [
    (0.0000019, '0.00019%'),
    (0.000006,  '0.0006%'),
    (0.0013,    '0.13%'),
    (0.0027,    '0.3%'),
    (0.0019,    '0.19%'),
    (0.00089,   '0.09%'),
    (0.0002,    '0.02%'),
    (0.000002,  '0.0002%'),
    (0.00001,   '0.001%'),
    (0.005,     '0.5%'),
    (0.0099,    '1.0%'),
    (0.01,      '1.0%'),
    (0.0,       '0%'),
]


def test_float2percent():
    for frac, expected in FLOAT2PERCENT_CASES:
        assert float2percent(frac) == expected, (frac, float2percent(frac), expected)


if __name__ == '__main__':
    test_float2percent()
    print('OK')
