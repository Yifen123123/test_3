import re
from datetime import date

# ===== 身分證檢查碼 =====
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

# ===== 電話抽取與正規化 =====
# 支援：
# (03) 12345678 轉 123
# 02-12345678轉123或456
# 0212345678#123
# 03 1234567、(02)1234-5678 等
PHONE_PATTERNS = [
    r'\(?(0\d{1,2})\)?[ \-]?(\d{3,4})[ \-]?(\d{3,4})(?:[ \-]*(?:轉|ext\.?|#|分機)[ \-]?(?:([0-9\-、或/]{1,10})))?',
]
PHONE_RE = re.compile('|'.join(f'(?:{p})' for p in PHONE_PATTERNS))

def normalize_phone(m: re.Match) -> str:
    # 取出群組：1區碼, 2前段, 3後段, 4分機（可能含「或」）
    area, p1, p2, ext = m.group(1), m.group(2), m.group(3), m.group(4)
    base = f"{area}-{p1}{p2}"
    if ext:
        # 將「或」「、」「/」保留為「或」提示
        ext_norm = ext.replace('、', '或').replace('/', '或')
        return f"{base}#{ext_norm}"
    return base

def extract_phone(text: str) -> str | None:
    # 在「電話/聯絡/承辦」附近優先
    for kw in ['電話', '聯絡', '分機', '承辦', '書記官']:
        for m in PHONE_RE.finditer(text):
            span = m.span()
            ctx = text[max(0, span[0]-15):min(len(text), span[1]+15)]
            if kw in ctx:
                return normalize_phone(m)
    # 否則抓第一個
    m = PHONE_RE.search(text)
    return normalize_phone(m) if m else None

# ===== 承辦資訊抽取（職稱或姓名）=====
ROLE_WORDS = ['書記官','承辦人','聯絡人','承辦','股員','股長','專員']
NAME_HINT = r'[^\s，、()（）]{2,4}'  # 2-4字中文名的寬鬆提示
DATE_ROC_RE = re.compile(r'民國\s*(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日')
DATE_ISO_RE = re.compile(r'(20\d{2})[./\-年]?\s*(\d{1,2})[./\-月]?\s*(\d{1,2})\s*日?')

def normalize_date_roc_to_iso(y:int, m:int, d:int) -> str | None:
    try:
        y = 1911 + y
        return datetime(y, m, d).strftime("%Y-%m-%d")
    except Exception:
        return None

def extract_doc_date(text: str) -> str | None:
    """
    依關鍵詞就近抓一組日期；支援民國/西元多種寫法。
    優先關鍵詞：發文日期/發文日/來文日期/來文日/發文時間/來文時間
    """
    KEYWORDS = ['發文日期','發文日','來文日期','來文日','發文時間','來文時間']
    # 先掃有關鍵詞的區域
    for m in re.finditer('|'.join(map(re.escape, KEYWORDS)), text):
        start, end = m.start(), m.end()
        win = text[max(0, start-20):min(len(text), end+30)]
        # 民國優先
        m1 = DATE_ROC_RE.search(win)
        if m1:
            y, mm, dd = map(int, m1.groups())
            iso = normalize_date_roc_to_iso(y, mm, dd)
            if iso: return iso
        # 西元
        m2 = DATE_ISO_RE.search(win)
        if m2:
            y, mm, dd = map(int, m2.groups())
            try:
                return datetime(y, mm, dd).strftime("%Y-%m-%d")
            except Exception:
                pass
    # 無關鍵詞時，降級為全文第一組日期
    m1 = DATE_ROC_RE.search(text)
    if m1:
        y, mm, dd = map(int, m1.groups())
        return normalize_date_roc_to_iso(y, mm, dd)
    m2 = DATE_ISO_RE.search(text)
    if m2:
        y, mm, dd = map(int, m2.groups())
        try:
            return datetime(y, mm, dd).strftime("%Y-%m-%d")
        except Exception:
            return None
    return None

def extract_officer(text: str) -> tuple[str|None, str|None]:
    # 標記型態：「承辦人：王小明」、「書記官：林OO」、「聯絡人：張小姐」
    m = re.search(rf'({"|".join(ROLE_WORDS)})[：:]\s*({NAME_HINT})', text)
    if m:
        role = m.group(1)
        name = m.group(2)
        # 濾掉太明顯不是姓名的詞彙（可視情況擴充）
        if len(name) > 5 or '電話' in name:
            name = None
        return role, name
    # 只有職稱出現
    m = re.search(rf'({"|".join(ROLE_WORDS)})[：:]?', text)
    if m:
        return m.group(1), None
    return None, None

# ===== 發文字號抽取（來文）=====
# 支援：發文字號：XXX、文號：XXX、○字第XXXX號、○○府授人字第…號 等
DOCNO_CANDIDATE_RE = re.compile(
    r'(?:發文字號|文號)[：:]\s*([^\n\r，。、]{4,30})'
    r'|([一二三四五六七八九十○零〇台臺北新高桃竹苗中彰投雲嘉南高屏宜花東金馬\w]{1,6}字第[^\s，。、]{3,20}號)'
)

def extract_doc_no(text: str) -> str | None:
    for m in DOCNO_CANDIDATE_RE.finditer(text):
        g = next((x for x in m.groups() if x), None)
        if g:
            # 清理尾端標點
            return g.strip().strip('，。；；、 ')
    return None

def today_fields():
    t = date.today()
    return {
        "today_yyyy": f"{t.year}",
        "today_mm": f"{t.month:02d}",
        "today_dd": f"{t.day:02d}",
        "today_iso": t.isoformat(),
        "today_yyyymmdd": t.strftime("%Y%m%d"),
    }

import re
from typing import Optional

_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９／．－", "0123456789/.-")

def _to_halfwidth(s: str) -> str:
    return (s or "").translate(_FULLWIDTH_DIGITS)

def _pad2(n: int) -> str:
    return f"{n:02d}"

def _roc_to_ad(y: int) -> int:
    # ROC 1年=1912年，通常文書以1911偏移處理
    return y + 1911

def _parse_date_like(token: str) -> Optional[str]:
    """
    支援：
      - 100年09月09日 / 112/7/1 / 112.07.01 / 1120701（皆視為民國）
      - 2024-7-1 / 2024/07/01 / 2024.07.01（西元）
    回傳 yyyy-mm-dd 或 None
    """
    t = _to_halfwidth(token).strip()

    # 1) ROC: YYY年MM月DD日
    m = re.search(r"(?P<y>\d{2,3})\s*年\s*(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日?", t)
    if m:
        y, mth, d = int(m.group("y")), int(m.group("m")), int(m.group("d"))
        return f"{_roc_to_ad(y)}-{_pad2(mth)}-{_pad2(d)}"

    # 2) ROC with separators: 112/7/1 或 112.07.01 或 112-7-1
    m = re.search(r"(?P<y>\d{2,3})[./-](?P<m>\d{1,2})[./-](?P<d>\d{1,2})", t)
    if m:
        y, mth, d = int(m.group("y")), int(m.group("m")), int(m.group("d"))
        return f"{_roc_to_ad(y)}-{_pad2(mth)}-{_pad2(d)}"

    # 3) ROC compact: 1120701 或 0990909
    m = re.search(r"\b(?P<y>\d{2,3})(?P<m>\d{2})(?P<d>\d{2})\b", t)
    if m and len(m.group("y")) in (2, 3):
        y, mth, d = int(m.group("y")), int(m.group("m")), int(m.group("d"))
        return f"{_roc_to_ad(y)}-{_pad2(mth)}-{_pad2(d)}"

    # 4) AD: 2024-07-01 / 2024/7/1 / 2024.7.1
    m = re.search(r"(?P<y>20\d{2})[./-](?P<m>\d{1,2})[./-](?P<d>\d{1,2})", t)
    if m:
        y, mth, d = int(m.group("y")), int(m.group("m")), int(m.group("d"))
        return f"{y}-{_pad2(mth)}-{_pad2(d)}"

    # 5) AD: 2024年7月1日
    m = re.search(r"(?P<y>20\d{2})\s*年\s*(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日?", t)
    if m:
        y, mth, d = int(m.group("y")), int(m.group("m")), int(m.group("d"))
        return f"{y}-{_pad2(mth)}-{_pad2(d)}"

    return None

def extract_reference_date(raw_text: str) -> Optional[str]:
    """
    針對『查調日/申報基準日/基準日：』等標籤式寫法加強擷取。
    會優先找帶冒號（：或:）的標籤後的日期字串。
    """
    if not raw_text:
        return None
    text = _to_halfwidth(raw_text.replace("\u3000", " "))

    # 1) 直接標籤 + 冒號
    #   例：查調日（申報基準日）：100年09月09日
    #       基準日: 112.7.1
    for m in re.finditer(r"(查調日|申報基準日|基準日)\s*[:：]\s*([^\n\r，。；；]+)", text):
        cand = m.group(2).strip()
        parsed = _parse_date_like(cand)
        if parsed:
            return parsed

    # 2) 標籤後面若不是同一段，往後10~30字內找日期
    for m in re.finditer(r"(查調日|申報基準日|基準日)[）\)]?\s*[:：]?", text):
        span_end = m.end()
        window = text[span_end: span_end + 40]
        parsed = _parse_date_like(window)
        if parsed:
            return parsed

    # 3) 鄰近人別式備援（姓名/身分證後面 40 字內）
    for m in re.finditer(r"[A-Z][12]\d{8}|[一-龥]{2,4}[○Ｏ\*]{0,2}", text):
        span_end = m.end()
        window = text[span_end: span_end + 40]
        if re.search(r"(基準日|查調日|申報基準日)", window):
            parsed = _parse_date_like(window)
            if parsed:
                return parsed

    return None
