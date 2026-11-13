"""Fonctions 1, 2 et 3 : estimation de la facture, consommation attendue et détection d'anomalies.
"""
import numpy as np
import pandas as pd

from donnees import D, P, GOUV, UNITE, profil



# ===================== fonction 1 =====================
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import cross_val_score

M_FACTURE = {}
for r, d in D.items():
    X = d[["conso_periode", "nb_mois"]]
    mae = -cross_val_score(LinearRegression(), X, d.montant_facture_dt, cv=5, scoring="neg_mean_absolute_error").mean()
    base = (d.montant_facture_dt - d.montant_facture_dt.median()).abs().mean()
    M_FACTURE[r] = LinearRegression().fit(X, d.montant_facture_dt)
    print(f"{r:<12} erreur moyenne : {mae:.1f} DT  |  référence (médiane) : {base:.1f} DT")

def fonction1(ressource, index_ancien, index_actuel, jours_ecoules, jours_periode=90):
    """Projette la consommation sur la période puis estime la facture."""
    conso_proj = max((index_actuel - index_ancien) / jours_ecoules * jours_periode, 0)
    nb_mois = round(jours_periode / 30)
    f = lambda c: max(float(M_FACTURE[ressource].predict(pd.DataFrame({"conso_periode": [c], "nb_mois": [nb_mois]}))[0]), 0)
    facture, facture_10 = f(conso_proj), f(conso_proj * 0.9)
    return {"conso_projetee_periode": round(conso_proj, 1), "facture_estimee_DT": round(facture, 1),
            "economie_si_-10%_DT": round(facture - facture_10, 1)}




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

def fonction2(ressource, nb_pers, surface, gouv, ma_conso_mensuelle):
    normal = attendue(ressource, nb_pers, surface, gouv)
    ratio = ma_conso_mensuelle / normal
    niveau = ("économe" if ratio < 0.7 else "normal" if ratio < 1.3
              else "élevé" if ratio < 2 else "gros consommateur")
    return {"foyers_semblables": round(normal, 1), "ma_conso": ma_conso_mensuelle,
            "niveau": niveau, "objectif": round(min(normal, ma_conso_mensuelle), 1)}




# ===================== fonction 3 =====================
SEUIL = 2.5     # alerte anomalie si conso > SEUIL x consommation attendue
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]
SAISON = {r: d.groupby("mois").conso_mensuelle.mean() for r, d in D.items()}
CONSEIL = {"Eau": "réduisez l'arrosage", "Electricité": "réduisez la climatisation"}

def fonction3(ressource, nb_pers, surface, gouv, conso_actuelle, mois_actuel, conso_precedente=None):
    alertes, s = [], SAISON[ressource]
    if mois_actuel in s.nlargest(2).index:
        alertes.append(f" Pic : {MOIS[s.idxmax()-1]} est le mois le plus chargé, {CONSEIL.get(ressource, 'réduisez votre consommation')}.")
    if conso_actuelle > SEUIL * attendue(ressource, nb_pers, surface, gouv):
        alertes.append(" Anomalie : consommation très supérieure aux foyers semblables, vérifiez une fuite ou un défaut.")
    if conso_precedente and conso_actuelle >= 2 * conso_precedente:
        alertes.append(" Rupture : votre consommation a doublé, vérifiez une fuite ou un défaut.")
    return alertes or [" Rien à signaler."]

