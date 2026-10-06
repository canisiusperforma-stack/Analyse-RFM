import sys, io
sys.path.insert(0, ".")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from app.ai.response_validator import _iterer_nombres, MOTIF_NOMBRE

tests = {
  "isole nbsp": "1\u00a0250\u00a000\u00a000\u00a000 Ar",
  "avec prefixe": "Montant : 1\u00a0250\u00a000\u00a000\u00a000 Ar",
  "apres etroit": "1\u202f250\u202f000\u202f000 Ar et 1\u00a0250\u00a000\u00a000\u00a000 Ar",
}
for nom, s in tests.items():
    print(nom)
    for m, v, d in _iterer_nombres(s):
        print("   ", ascii(m.group(0)), "span", m.span(), "->", v)
print()
print("pattern identique ? ", MOTIF_NOMBRE.flags)
