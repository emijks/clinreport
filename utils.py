import pandas as pd
import socket
from math import floor, log10

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
    p = 100 * f
    if p <= 0:
        return '0%'
    exp = floor(log10(p))
    if p < 10 ** exp:
        exp -= 1
    elif p >= 10 ** (exp + 1):
        exp += 1
    lead = int(p / 10 ** exp)
    sig = 2 if lead == 1 else 1
    ndigits = sig - 1 - exp
    return f'{round(p, ndigits)}%'

# Move to database.py?
def get_ru_annotations(timeout: int = 10) -> dict | None:
    socket.setdefaulttimeout(timeout)
    url = 'https://docs.google.com/spreadsheets/d/1Zj_Gw-TolcoKljqfk4eCrQ1hyhlZDs44UOZbFTVTfes'
    ru_annotations = {
        'omim': pd.read_csv(f'{url}/export?format=csv&gid=0', index_col=0).to_dict(),
        'secondary': pd.read_csv(f'{url}/export?format=csv&gid=706494431', index_col=0).to_dict()
    }
    return ru_annotations
