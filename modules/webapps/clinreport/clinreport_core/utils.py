from decimal import Decimal


def predict_insilico(scsnvada, metarnn, revel, alphamissense, phylop):
    thresholds = {
        'scsnvada': (0.957813, 0.999322, 0.999925),
        'metarnn': (0.748, 0.841, 0.939),
        'revel': (0.644, 0.773, 0.932),
        'alphamissense': (0.787, 0.956, 0.994),
        'phylop': (7.52, 9.88, float('inf')),
    }
    if scsnvada:
        return True if scsnvada >= thresholds['scsnvada'][0] else False
    if metarnn:
        return True if metarnn >= thresholds['metarnn'][0] else False
    if revel:
        return True if revel >= thresholds['revel'][0] else False
    if alphamissense:
        return True if alphamissense >= thresholds['alphamissense'][0] else False
    if phylop:
        return True if phylop >= thresholds['phylop'][0] else False
    return False


def float2percent(f: float) -> str:
    p = Decimal(str(f)).scaleb(2)
    if p <= 0:
        return '0%'
    if p < 1:
        # Scientific notation rounds to two significant digits across powers of ten.
        p = Decimal(f'{p:.1E}')
        return f'{p:f}%'.replace('.', ',')
    return f'{p:.1f}%'.replace('.', ',')
