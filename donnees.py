"""Étapes 1 et 2 : chargement et nettoyage des données .
"""
import os
import sys

import numpy as np
import pandas as pd


BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))  # _MEIPASS = dossier de l'.exe
FICHIER = os.path.join(BASE, "dataset_regenere.xlsx")

df = pd.read_excel(FICHIER)

# ===================== Chargement et nettoyage des données =====================
df = pd.read_excel(FICHIER)
n0 = len(df)

# --- Vérification des colonnes ---
COLS = ["ressource", "gouvernorat", "date_debut", "date_fin", "nb_mois", "conso_mensuelle",
        "nb_personnes_est", "superficie_m2_est", "montant_facture_dt"]
manquantes = [c for c in COLS if c not in df.columns]
assert not manquantes, f"Colonnes introuvables : {manquantes}\nColonnes présentes : {list(df.columns)}"

# --- Lecture robuste des dates (2025-08-01 ou 15/03/2024) ---
def lire_date(col):
    s = col.astype(str).str.strip()
    d = pd.to_datetime(s, format="ISO8601", errors="coerce")
    reste = d.isna()
    d[reste] = pd.to_datetime(s[reste], format="mixed", dayfirst=True, errors="coerce")
    return d

for c in ["date_debut", "date_fin"]:
    df[c] = lire_date(df[c])

# --- Colonnes numériques (accepte aussi "12,5" avec virgule) ---
NUM = ["nb_mois", "conso_mensuelle", "nb_personnes_est", "superficie_m2_est", "montant_facture_dt"]
for c in NUM:
    df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", "."), errors="coerce")

# --- Diagnostic puis nettoyage ---
cles = ["date_debut", "date_fin"] + NUM
df = df.dropna(subset=cles)
n_futur = (df.date_fin > pd.Timestamp.today()).sum()
df = df[(df.date_fin <= pd.Timestamp.today()) & (df.conso_mensuelle > 0) & (df.nb_mois > 0)].copy()

df["mois"] = (df.date_debut + (df.date_fin - df.date_debut) / 2).dt.month
df["conso_periode"] = df.conso_mensuelle * df.nb_mois
GOUV = sorted(df.gouvernorat.unique())
UNITE = {"Eau": "m³", "Electricité": "kWh"}          # SONEDE = eau, STEG = électricité

def profil(nb_pers, surface, gouv):
    return [nb_pers, surface] + [int(gouv == g) for g in GOUV]

# Un jeu de données par ressource (eau / électricité)
D = {r: df[df.ressource == r].copy() for r in sorted(df.ressource.unique())}
P = {r: np.array([profil(x.nb_personnes_est, x.superficie_m2_est, x.gouvernorat) for x in d.itertuples()], dtype=float)
     for r, d in D.items()}

