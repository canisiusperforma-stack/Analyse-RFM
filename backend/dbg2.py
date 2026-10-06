import re
motif = re.compile(
    r"(?<![\w])"
    r"(?P<signe>[+-]?)"
    r"(?P<corps>"
    r"\d{1,3}(?:[.,]\d{3}){2,}(?:[.,]\d+)?"
    r"|\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d+)?"
    r"|\d+(?:[.,]\d+)?"
    r")"
    r"\s*(?P<suffixe>md|MD|Md|[kKmM])?"
    r"(?!\w)",
    re.VERBOSE,
)
for nom, sp in [("espace", " "), ("nbsp", "\u00a0"), ("etroit", "\u202f")]:
    s = f"1{sp}250{sp}000{sp}000 Ar"
    m = motif.search(s)
    print(f"{nom:8} source={ascii(s)}  match={ascii(m.group(0)) if m else None}")
print()
print("test char par char de la classe, sans VERBOSE:")
motif2 = re.compile(r"\d{1,3}(?:[ \u00a0\u202f]\d{3})+")
for nom, sp in [("espace"," "), ("nbsp","\u00a0"), ("etroit","\u202f")]:
    s = f"1{sp}250{sp}000{sp}000"
    m = motif2.search(s)
    print(f"  {nom:8} -> {ascii(m.group(0)) if m else None}")
