from clinreport_core.utils import float2percent

FLOAT2PERCENT_CASES = [
    (0.0000019, '0,00019%'),
    (0.00000449, '0,00045%'),
    (0.0013,    '0,13%'),
    (0.0027,    '0,27%'),
    (0.0019,    '0,19%'),
    (0.00089,   '0,089%'),
    (0.0002,    '0,020%'),
    (0.005,     '0,50%'),
    (0.0000999, '0,010%'),
    (0.009999,  '1,0%'),
    (0.01,      '1,0%'),
    (0.0123,    '1,2%'),
    (0.0569822579785817, '5,7%'),
    (0.59,      '59,0%'),
    (0.0,       '0%'),
]


def test_float2percent():
    for frac, expected in FLOAT2PERCENT_CASES:
        assert float2percent(frac) == expected, (frac, float2percent(frac), expected)


if __name__ == '__main__':
    test_float2percent()
    print('OK')
