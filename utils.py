import re
from datetime import date

LETTER_MAP = {
    'A':10,'B':11,'C':12,'D':13,'E':14,'F':15,'G':16,'H':17,'I':34,
    'J':18,'K':19,'L':20,'M':21,'N':22,'O':35,'P':23,'Q':24,'R':25,
    'S':26,'T':27,'U':28,'V':29,'W':32,'X':30,'Y':31,'Z':33
}
ID_RE = re.compile(r'\b([A-Z])[12]\d{8}\b')

def validate_tw_id(twid: str) -> bool:
    m = ID_RE.fullmatch(twid)
    if not m:
        return False
    letter = m.group(1)
    nums = [int(x) for x in twid[1:]]  # 9 digits
    code = LETTER_MAP.get(letter)
    if code is None:
        return False
    a1, a2 = divmod(code, 10)
    weights = [1,9,8,7,6,5,4,3,2,1,1]  # A1,A2,d1..d9
    digits = [a1, a2] + nums
    return sum(w*d for w, d in zip(weights, digits)) % 10 == 0

def today_fields():
    t = date.today()
    return {
        "today_yyyy": f"{t.year}",
        "today_mm": f"{t.month:02d}",
        "today_dd": f"{t.day:02d}",
        "today_iso": t.isoformat(),
        "today_yyyymmdd": t.strftime("%Y%m%d"),
    }
