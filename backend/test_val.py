import sys, io
sys.path.insert(0, ".")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from app.ai.response_validator import valider_reponse

NB = "\u00a0"; ET = "\u202f"
def groupes(sp, n):  # 1 250 000 000 -> 1 + 3 groupes de 3
    return f"1{sp}250" + (f"{sp}000" * n)

faits = {
    "exercice": 2024, "calcule_le": "2024-05-01T12:00:00+00:00",
    "budget": {"credits_ouverts": 1250000000.0, "taux_execution": 0.6234, "solde": -150000000.0},
    "remboursements": {"demandes": 1234, "montant_demande": 875000000.0, "taux_acceptation": 0.7812},
    "analytique": [{"cle":"taux","message":"Taux de 62,3 % sur 1 250 000 000 Ar."},
                   {"cle":"depassement","message":"Depassement de 150 000 000 Ar."}],
}
print("nbsp   :", ascii(groupes(NB,2)), "->", valider_reponse(groupes(NB,2), faits).valide)
print("etroit :", ascii(groupes(ET,2)), "->", valider_reponse(groupes(ET,2), faits).valide)
print("espaces:", ascii(groupes(" ",2)), "->", valider_reponse(groupes(" ",2), faits).valide)

def t(nom, txt, att):
    r = valider_reponse(txt, faits)
    ok = r.valide == att
    print(f"{'OK ' if ok else 'KO '} {nom:26} valide={str(r.valide):5} ecarts={[e.brut for e in r.ecarts]}")
    return ok
r=[]
print("\n--- LEGITIMES (12) ---")
r+=[t("taux pourcentage","Le taux est de 62,3 % pour 1 250 000 000 Ar.",True),
    t("milliards Md","Soit 1,25 Md de credits.",True),
    t("milliers k","Soit 1 250 000 k de credits.",True),
    t("arrondi entier","Le taux est de 62 %.",True),
    t("proportion brute","La proportion est de 0,6234.",True),
    t("valeur absolue","Depassement de 150 000 000 Ar.",True),
    t("ordinal","Les 3 axes et les 2 priorites.",True),
    t("annee","Sur l exercice 2024, la population est stable.",True),
    t("espaces insecables",f"{groupes(ET,2)} Ar et {groupes(NB,2)} Ar et {groupes(' ',2)} Ar.",True),
    t("effectif","1234 demandes de remboursement.",True),
    t("ISO date","Calcule le 2024-05-01.",True),
    t("taux brut decimal","Le taux d acceptation atteint 78,12 %.",True)]
print("\n--- INVENTIONS (11) ---")
r+=[t("montant invente","Le budget est de 2 500 000 000 Ar.",False),
    t("taux invente","Le taux atteint 87,5 %.",False),
    t("effectif invente","Nous recensons 4 321 beneficiaires.",False),
    t("moyenne inventee","Le montant moyen est de 750 000 Ar.",False),
    t("petit entier invente","Il reste 42 demandes en attente.",False),
    t("abrev mal placee","Les credits sont de 1,25 M Ar.",False),
    t("milliers fantomes","Soit 1 250 000 Ar seulement.",False),
    t("chiffre anglais","Total de 1.234.567 Ar.",False),
    t("decalage decimal","La moyenne est de 78,12 Ar et non 87,5.",False),
    t("double du reel","Les credits ouverts sont de 2 500 000 000 Ar.",False),
    t("troncature","Les credits ouverts sont de 1 250 000 Ar.",False)]
print(f"\nRESULTAT : {sum(r)}/{len(r)}")
