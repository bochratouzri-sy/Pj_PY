#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse

import numpy as np
import pandas as pd

COLONNES = [
    "id", "fournisseur", "ressource", "foyer_ref", "gouvernorat",
    "superficie_m2_est", "nb_personnes_est", "date_debut", "date_fin",
    "nb_mois", "index_ancien", "index_nouveau", "conso_mensuelle",
    "montant_facture_dt",
]

#  Foyers (profil commun a la STEG et a la SONEDE)
def generer_foyers(rng, nb_foyers):
    """Cree F01..Fnn : gouvernorat, superficie et nombre de personnes."""
    surfaces = np.array([60, 90, 100, 110, 120, 130, 140, 150, 160, 170,
                         190, 195, 220, 250, 300, 360, 400])
    foyers = []
    for i in range(1, nb_foyers + 1):
        u = i / nb_foyers
        gouv = "Ariana" if u <= 0.6 else "Nabeul"
        if i == nb_foyers - 3:            # un foyer isole (comme F39 Sousse)
            gouv = "Sousse"
        foyers.append({
            "foyer_ref": f"F{i:02d}",
            "gouvernorat": gouv,
            "superficie_m2_est": int(rng.choice(surfaces)),
            "nb_personnes_est": int(rng.choice(
                [1, 2, 3, 4, 5, 6, 8], p=[.07, .15, .25, .25, .15, .09, .04])),
        })
    return pd.DataFrame(foyers)


# 2. Partie SONEDE (eau)
def generer_sonede(rng, foyers, annee_min=2012, annee_max=2026):
    """Releves trimestriels : nb_mois = 3, tarif ~ 1.4 a 2.3 DT/m3."""
    lignes = []
    for f in foyers.itertuples():
        # Ariana : 1-2 releves ; Nabeul : jusqu'a 6 (residences suivies plus longtemps)
        n = int(rng.integers(1, 3)) if f.gouvernorat == "Ariana" else int(rng.integers(1, 7))
        if rng.random() < 0.15:           # certains foyers n'ont pas de facture d'eau
            continue
        debut = pd.Timestamp(
            year=int(rng.integers(annee_min, annee_max)),
            month=int(rng.integers(1, 13)), day=1)
        index = int(rng.integers(50, 7000))
        # consommation de base (m3/mois) selon le nombre de personnes
        base = max(1.0, f.nb_personnes_est * rng.uniform(2.0, 4.0))
        for _ in range(n):
            fin = debut + pd.DateOffset(months=3) - pd.Timedelta(days=1)
            saison = 1.25 if debut.month in (5, 6, 7, 8) else 0.9
            conso_m = max(0.0, rng.lognormal(np.log(base * saison), 0.45))
            conso_tot = int(round(conso_m * 3))
            tarif = rng.uniform(1.4, 2.3)
            lignes.append({
                "fournisseur": "SONEDE", "ressource": "Eau",
                "foyer_ref": f.foyer_ref, "gouvernorat": f.gouvernorat,
                "superficie_m2_est": f.superficie_m2_est,
                "nb_personnes_est": f.nb_personnes_est,
                "date_debut": debut, "date_fin": fin, "nb_mois": 3,
                "index_ancien": index, "index_nouveau": index + conso_tot,
                "montant_facture_dt": round(conso_tot * tarif + rng.uniform(2, 8), 1),
            })
            index += conso_tot
            debut = fin + pd.Timedelta(days=1)
            if debut.year > annee_max:
                break
    return pd.DataFrame(lignes)

# 3. Partie STEG (electricite)
def generer_steg(rng, foyers, annee_min=2014, annee_max=2026):
    """Periodes de 2, 4, 6, 8, 12... mois ; tarif progressif 0.22 a 0.45 DT/kWh."""
    lignes = []
    for f in foyers.itertuples():
        if rng.random() < 0.08:           # foyer sans facture STEG
            continue
        n = int(rng.integers(1, 3)) if f.gouvernorat == "Ariana" else int(rng.integers(1, 7))
        debut = pd.Timestamp(
            year=int(rng.integers(annee_min, annee_max)),
            month=int(rng.integers(1, 13)), day=int(rng.integers(15, 28)))
        index = int(rng.integers(10_000, 55_000))
        base = 30 + f.nb_personnes_est * 14 + f.superficie_m2_est * 0.12   # kWh/mois
        for _ in range(n):
            nb_mois = int(rng.choice([2, 2, 4, 4, 6, 8, 12, 16],
                                     p=[.2, .15, .2, .15, .12, .08, .07, .03]))
            fin = debut + pd.DateOffset(months=nb_mois) - pd.Timedelta(days=1)
            saison = 1.3 if debut.month in (6, 7, 8) else 1.0
            conso_m = max(0.0, rng.lognormal(np.log(base * saison), 0.35))
            conso_tot = int(round(conso_m * nb_mois))
            # tarif progressif : plus on consomme par mois, plus le DT/kWh monte
            tarif = 0.23 if conso_m <= 100 else 0.28 if conso_m <= 200 else 0.40
            lignes.append({
                "fournisseur": "STEG", "ressource": "Electricité",
                "foyer_ref": f.foyer_ref, "gouvernorat": f.gouvernorat,
                "superficie_m2_est": f.superficie_m2_est,
                "nb_personnes_est": f.nb_personnes_est,
                "date_debut": debut, "date_fin": fin, "nb_mois": nb_mois,
                "index_ancien": index, "index_nouveau": index + conso_tot,
                "montant_facture_dt": round(conso_tot * tarif + nb_mois * rng.uniform(0.3, 1.2), 3),
            })
            index += conso_tot
            debut = fin + pd.Timedelta(days=1)
            if debut.year > annee_max:
                break
    return pd.DataFrame(lignes)

# 4. Fusion STEG + SONEDE dans un seul tableau
def fusionner(sonede, steg):
    df = pd.concat([sonede, steg], ignore_index=True)
    df["conso_mensuelle"] = ((df["index_nouveau"] - df["index_ancien"]) / df["nb_mois"]).round(3)
    df.insert(0, "id", np.arange(1, len(df) + 1))
    return df[COLONNES]


def injecter_anomalies(rng, df, taux):
    """Reproduit les defauts du fichier brut (index fige, montant aberrant,
    dates inversees, valeurs vides, espaces parasites)."""
    df = df.copy()
    df["date_debut"] = df["date_debut"].astype(object)
    n = max(1, int(len(df) * taux))
    for i in rng.choice(df.index, size=n, replace=False):
        t = rng.choice(["index_fige", "montant", "dates", "vide", "espaces"])
        if t == "index_fige":
            df.loc[i, "index_nouveau"] = df.loc[i, "index_ancien"]
        elif t == "montant":
            df.loc[i, "montant_facture_dt"] = round(df.loc[i, "montant_facture_dt"] * rng.uniform(8, 15), 1)
        elif t == "dates":
            df.loc[i, "date_debut"], df.loc[i, "date_fin"] = df.loc[i, "date_fin"], df.loc[i, "date_debut"]
        elif t == "vide":
            df.loc[i, "conso_mensuelle"] = np.nan
        else:
            df.loc[i, "foyer_ref"] = f" {df.loc[i, 'foyer_ref']} "
    return df

# 5. Controles qualite -> "Donnees" / "A_verifier"
def controler(df):
    df = df.copy()
    notes = [[] for _ in range(len(df))]

    for col in ("foyer_ref", "fournisseur", "ressource", "gouvernorat"):
        nettoye = df[col].astype(str).str.strip()
        for k in np.where(nettoye.values != df[col].astype(str).values)[0]:
            notes[k].append("Espaces parasites supprimes")
        df[col] = nettoye

    d1 = pd.to_datetime(df["date_debut"], errors="coerce")
    d2 = pd.to_datetime(df["date_fin"], errors="coerce")
    ia = pd.to_numeric(df["index_ancien"], errors="coerce")
    inn = pd.to_numeric(df["index_nouveau"], errors="coerce")

    for k in range(len(df)):
        if d2.iloc[k] < d1.iloc[k]:
            notes[k].append("Date de fin avant debut")
        else:
            mois = (d2.iloc[k].year - d1.iloc[k].year) * 12 + d2.iloc[k].month - d1.iloc[k].month + 1
            if abs(mois - df["nb_mois"].iloc[k]) > 1:
                notes[k].append("Nombre de mois a verifier")
        if pd.isna(df["conso_mensuelle"].iloc[k]):
            notes[k].append("Valeur vide | Consommation vide")
        if inn.iloc[k] <= ia.iloc[k]:
            notes[k].append("Consommation a verifier")
        tarif = df["montant_facture_dt"].iloc[k] / max(inn.iloc[k] - ia.iloc[k], 1)
        limite = 4 if df["fournisseur"].iloc[k] == "SONEDE" else 1.5
        if tarif > limite:
            notes[k].append("Montant a verifier")

    df["date_debut"], df["date_fin"] = d1, d2
    suspect = np.array([bool(set(n) - {"Espaces parasites supprimes"}) for n in notes])
    df["correction"] = [" | ".join(n) if n else "OK" for n in notes]
    donnees = df.loc[~suspect, COLONNES].reset_index(drop=True)
    a_verifier = df.loc[suspect].reset_index(drop=True)
    return donnees, a_verifier

# 6. Ecriture du fichier unique
def ecrire(donnees, a_verifier, chemin):
    donnees, a_verifier = donnees.copy(), a_verifier.copy()
    for tab in (donnees, a_verifier):          # dates sans heure
        for col in ("date_debut", "date_fin"):
            tab[col] = pd.to_datetime(tab[col], errors="coerce").dt.date
    with pd.ExcelWriter(chemin, engine="openpyxl") as xw:
        donnees.to_excel(xw, sheet_name="Donnees", index=False)
        a_verifier.to_excel(xw, sheet_name="A_verifier", index=False)
        for ws in xw.book.worksheets:
            ws.freeze_panes = "A2"
            for nom in ("date_debut", "date_fin"):     # format affiche : AAAA-MM-JJ
                idx = [c.value for c in ws[1]].index(nom) + 1
                for row in range(2, ws.max_row + 1):
                    ws.cell(row=row, column=idx).number_format = "yyyy-mm-dd"
            for col in ws.columns:
                largeur = max(len(str(c.value)) if c.value is not None else 0 for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(largeur + 2, 45)


def main():
    p = argparse.ArgumentParser(description="Regenere le dataset STEG + SONEDE.")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--nb-foyers", type=int, default=42)
    p.add_argument("--nb-lignes-min", type=int, default=0,
                   help="nombre minimum de lignes au total (augmente les foyers si besoin)")
    p.add_argument("--taux-anomalies", type=float, default=0.03,
                   help="part de lignes volontairement degradees (0 = aucune)")
    p.add_argument("--sortie", default="dataset_regenere.xlsx")
    a = p.parse_args()

    nb_foyers = a.nb_foyers
    while True:
        rng = np.random.default_rng(a.seed)
        foyers = generer_foyers(rng, nb_foyers)
        sonede = generer_sonede(rng, foyers)
        steg = generer_steg(rng, foyers)
        df = fusionner(sonede, steg)
        if len(df) >= a.nb_lignes_min:
            break
        nb_foyers += 10
    if a.taux_anomalies > 0:
        df = injecter_anomalies(rng, df, a.taux_anomalies)

    donnees, a_verifier = controler(df)
    ecrire(donnees, a_verifier, a.sortie)

    print(f"SONEDE : {len(sonede)} lignes | STEG : {len(steg)} lignes")
    print(f"Donnees : {len(donnees)} | A_verifier : {len(a_verifier)}")
    print(f"Fichier ecrit : {a.sortie}")


if __name__ == "__main__":
    main()
