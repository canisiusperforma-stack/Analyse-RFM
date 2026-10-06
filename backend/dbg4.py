import sys, io
sys.path.insert(0, ".")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from app.ai.response_validator import _iterer_nombres, construire_index

ET = "\u202f"; NB = "\u00a0"
s = f"Montant : 1{ET}250{ET}000{ET}000{ET}000 Ar."
print("source:", ascii(s))
for m, v, d in _iterer_nombres(s):
    print("  corps:", ascii(m.group("corps")), "| signe:", ascii(m.group("signe")),
          "| suffixe:", ascii(m.group("suffixe")), "=> valeur", repr(v), "dec", d)

faits = {"budget": {"credits_ouverts": 1250000000.0}}
idx = construire_index(faits)
print("\nvaleurs indexees:", idx._valeurs, idx._origines)
print("origine(1250000000.0, 0) ->", idx.origine(1250000000.0, 0))
