import sys, io, re
sys.path.insert(0, ".")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from app.ai.response_validator import MOTIF_NOMBRE, _analyser_nombre, _iterer_nombres

s = "Montant : 1\u202f250\u202f000\u202f000 Ar et 1\u00a0250\u00a000\u00a000\u00a000 Ar."
print("source:", ascii(s))
for m, v, d in _iterer_nombres(s):
    print("  match:", ascii(m.group(0)), "=> valeur", v, "dec", d)
print()
print("motif brut:", ascii(MOTIF_NOMBRE.pattern))
