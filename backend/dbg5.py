import sys, io, re
sys.path.insert(0, ".")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from app.ai.response_validator import _sans_separateurs, ESPACES_SEPARATEURS, _analyser_nombre

ET = "\u202f"
corps = f"1{ET}250{ET}000{ET}000{ET}000"
print("corps       :", ascii(corps), "len", len(corps))
print("sans_sep    :", ascii(_sans_separateurs(corps)))
print("ESPACES     :", [ascii(x) for x in ESPACES_SEPARATEURS])
print("rfind . ,   :", corps.rfind("."), corps.rfind(","))
print("split       :", re.split(r"[.,]", corps))
print("analyse     :", _analyser_nombre("", corps, ""))
