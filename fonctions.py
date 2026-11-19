"""Fonctions 1, 2 et 3 : estimation de la facture, consommation attendue et détection d'anomalies.
"""
import numpy as np
import pandas as pd

from donnees import D, P, GOUV, UNITE, profil



# ===================== fonction 1 =====================
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import cross_val_score

def _lignes_fiables(d):
    """Écarte les factures aberrantes (prix par unité hors IQR) et les consommations nulles."""
    pu = d.montant_facture_dt / d.conso_periode.where(d.conso_periode > 0)
    q1, q3 = pu.quantile([.25, .75])
    return d[(d.conso_mensuelle > 0) & pu.between(q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1))]

# Barème officiel SONEDE (arrêté de mars 2024) : prix par m3 appliqué à TOUT le volume du trimestre
BAREME_EAU = [(20, 0.200), (40, 0.740), (70, 1.040), (100, 1.490), (150, 1.770), (float("inf"), 2.310)]

def tarif_sonede(conso_trimestre):
    return conso_trimestre * next(p for lim, p in BAREME_EAU if conso_trimestre <= lim)

def _eau_trimestre(conso_periode, nb_mois):
    return tarif_sonede(conso_periode / nb_mois * 3)         # volume ramené à 1 trimestre

# Électricité : pas de barème dans le projet -> régression sur les lignes fiables
M_FACTURE, MARGE, PARAM_EAU = {}, {}, {}
for r, d in D.items():
    f = _lignes_fiables(d)
    if r == "Eau":
        # facture trimestrielle = K x tarif SONEDE + frais fixes (taxes, assainissement, redevance compteur)
        # constantes calibrées une fois sur les factures récentes (>= avril 2024) : elles ne dépendent donc plus du chargement des données
        PARAM_EAU["k"], PARAM_EAU["fixe"] = 1.17, 21
        rec = f[(f.date_fin >= "2024-04-01") & (f.nb_mois == 3)]
        base = rec.apply(lambda x: _eau_trimestre(x.conso_periode, x.nb_mois), axis=1)
        ecart = (rec.montant_facture_dt - (PARAM_EAU["k"] * base + PARAM_EAU["fixe"]))
    else:
        M_FACTURE[r] = LinearRegression().fit(f[["conso_mensuelle"]], f.montant_facture_dt / f.nb_mois)
        ecart = f.montant_facture_dt / f.nb_mois - M_FACTURE[r].predict(f[["conso_mensuelle"]])
    m = ecart.abs().quantile(.6)                           # 60 % des factures réelles sont à moins de m de l'estimation
    MARGE[r] = (-m, m)                                     # fourchette symétrique : l'estimation est toujours au milieu
    print(f"{r:<12} modèle facture entraîné sur {len(f)}/{len(d)} lignes fiables")

def _facture(ressource, conso, nb_mois):
    if ressource == "Eau":
        return max(PARAM_EAU["k"] * _eau_trimestre(conso, nb_mois) + PARAM_EAU["fixe"], 0) * nb_mois / 3
    return max(float(M_FACTURE[ressource].predict(pd.DataFrame({"conso_mensuelle": [conso / nb_mois]}))[0]), 0) * nb_mois

def fonction1(ressource, index_ancien, index_actuel, jours_ecoules, nb_mois=3):
    """Projette la consommation sur la période de facturation (nb_mois) puis estime la facture."""
    conso_proj = max((index_actuel - index_ancien) / jours_ecoules * (nb_mois * 30), 0)
    facture, facture_10 = _facture(ressource, conso_proj, nb_mois), _facture(ressource, conso_proj * 0.9, nb_mois)
    bas, haut = MARGE[ressource]
    mult = nb_mois / 3 if ressource == "Eau" else nb_mois     # la marge Eau est trimestrielle, celle de l'électricité mensuelle
    return {"conso_projetee_periode": round(conso_proj, 1), "facture_estimee_DT": round(facture, 1),
            "facture_min_DT": round(max(facture + bas * mult, 0), 1), "facture_max_DT": round(facture + haut * mult, 1),
            "economie_si_-10%_DT": round(facture - facture_10, 1), "nb_mois": nb_mois}




# ===================== fonction 2 =====================
M_CONSO = {}
for r, d in D.items():
    mae = -cross_val_score(LinearRegression(), P[r], d.conso_mensuelle, cv=5, scoring="neg_mean_absolute_error").mean()
    base = (d.conso_mensuelle - d.conso_mensuelle.median()).abs().mean()
    M_CONSO[r] = LinearRegression().fit(P[r], d.conso_mensuelle)
    print(f"{r:<12} erreur moyenne : {mae:.1f} {UNITE[r]}  |  référence (médiane) : {base:.1f} {UNITE[r]}")

def attendue(ressource, nb_pers, surface, gouv):
    """Consommation mensuelle attendue d'un foyer de ce profil."""
    return max(float(M_CONSO[ressource].predict([profil(nb_pers, surface, gouv)])[0]), 0.1)

SEUIL = 2.5     # alerte anomalie si conso > SEUIL x consommation attendue
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]
VERIFIER = {"Eau": "Vérifiez s'il y a une fuite (robinet, chasse d'eau, tuyau).",
            "Electricité": "Vérifiez vos appareils (climatiseur, chauffe-eau, réfrigérateur)."}

def fonction2(ressource, nb_pers, surface, gouv, ma_conso_mensuelle, conso_precedente=None, nb_mois=3):
    """Est-ce normal ? Compare aux foyers semblables (niveau) et prévient en langage simple (alertes).
    conso_precedente = consommation MENSUELLE de la période précédente (facultatif)."""
    normal = attendue(ressource, nb_pers, surface, gouv)
    ratio = ma_conso_mensuelle / normal
    niveau = ("économe" if ratio < 0.7 else "normal" if ratio < 1.3
              else "élevé" if ratio < 2 else "gros consommateur")
    alertes = []
    if ratio > SEUIL:
        alertes.append(f"Attention : votre consommation est plus de {str(SEUIL).replace('.', ',')} fois celle des foyers semblables. {VERIFIER.get(ressource, '')}")
    if conso_precedente and ma_conso_mensuelle >= 2 * conso_precedente:
        alertes.append(f"Attention : votre consommation a doublé par rapport à la période précédente. {VERIFIER.get(ressource, '')}")
    if ratio > 1.3:                                        # niveau « élevé » ou plus
        eco = _facture(ressource, ma_conso_mensuelle * nb_mois, nb_mois) - _facture(ressource, normal * nb_mois, nb_mois)
        if eco >= 1:
            alertes.append(f"Économie possible : vous consommez plus que les foyers semblables. En consommant comme eux, vous économiseriez "
                           f"environ {round(eco)} DT sur {nb_mois} mois (≈ {round(eco * 12 / nb_mois)} DT par an).")
    return {"foyers_semblables": round(normal, 1), "ma_conso": ma_conso_mensuelle, "niveau": niveau,
            "objectif": round(min(normal, ma_conso_mensuelle), 1),
            "alertes": alertes or ["Tout va bien : votre consommation est normale et stable. Continuez ainsi !"]}




# ===================== fonction 4 : budget =====================
def fonction4(ressource, budget, conso_periode, nb_mois=3):
    """Compare la facture projetée à un budget (DT) et dit de combien réduire pour le respecter."""
    u = UNITE[ressource]
    facture = _facture(ressource, conso_periode, nb_mois)
    if facture <= budget:
        reste = round(budget - facture)
        return {"depasse": False, "budget": budget, "facture": round(facture, 1), "ecart_DT": round(budget - facture, 1),
                "resume": "Dans le budget", "message": f"Vous êtes dans votre budget."}
    fixe = _facture(ressource, 0, nb_mois)
    depassement = round(facture - budget)
    if fixe > budget:
        return {"depasse": True, "budget": budget, "facture": round(facture, 1), "ecart_DT": round(facture - budget, 1),
                "resume": f"Dépasse de {depassement} DT",
                "message": f"Votre budget est inférieur aux frais fixes estimés (environ {round(fixe)} DT) : il ne peut pas être respecté, "
                           f"même sans consommer."}
    bas, haut = 0.0, float(conso_periode)                  # plus grande consommation qui respecte le budget (la facture augmente avec la conso)
    for _ in range(40):
        milieu = (bas + haut) / 2
        bas, haut = (milieu, haut) if _facture(ressource, milieu, nb_mois) <= budget else (bas, milieu)
    reduction = (conso_periode - bas) / nb_mois
    pct = round(100 * (conso_periode - bas) / conso_periode)
    return {"depasse": True, "budget": budget, "facture": round(facture, 1), "ecart_DT": round(facture - budget, 1),
            "resume": f"Dépasse de {depassement} DT",
            "message": f"À ce rythme, vous dépasserez votre budget de {depassement} DT. "
                       f"Réduisez d'environ {round(reduction, 1)} {u} par mois ({pct} %) pour rester dedans."}
