
"""
Regeneration combinee SONEDE + STEG.

Utilisation :
    python regenerer_complet.py dataset_nettoye.xlsx 500

Le nombre indique le nombre de nouvelles lignes par ressource :
    500 lignes SONEDE + 500 lignes STEG.

Sortie :
    dataset_final_regenere.xlsx

Le fichier source n'est jamais modifie.
"""

import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd


# =========================================================
# 1. PARAMETRES
# =========================================================

PATH = sys.argv[1] if len(sys.argv) > 1 else "dataset_nettoye.xlsx"
N_ROWS = int(sys.argv[2]) if len(sys.argv) > 2 else 500
SEED = 42
OUT = "dataset_final_regenere.xlsx"

rng = np.random.default_rng(SEED)


# =========================================================
# 2. OUTILS DE DETECTION DES COLONNES
# =========================================================

def normaliser(x):
    x = str(x).strip().lower()
    x = unicodedata.normalize("NFKD", x)
    x = "".join(c for c in x if not unicodedata.combining(c))
    return x.replace(" ", "_").replace("-", "_")


def trouver_colonne(df, noms):
    colonnes = {normaliser(c): c for c in df.columns}

    for nom in noms:
        if normaliser(nom) in colonnes:
            return colonnes[normaliser(nom)]

    # Recherche par prefixe, comme dans le code SONEDE.
    for nom in noms:
        prefixe = normaliser(nom)
        for c in df.columns:
            if normaliser(c).startswith(prefixe):
                return c

    return None


def nombre(serie):
    return pd.to_numeric(
        serie.astype(str)
        .str.replace(",", ".", regex=False)
        .str.replace(" ", "", regex=False),
        errors="coerce"
    )


def texte_normalise(serie):
    return serie.fillna("").astype(str).map(normaliser)


# =========================================================
# 3. LECTURE DU DATASET ORIGINAL
# =========================================================

source = Path(PATH)

if not source.exists():
    raise FileNotFoundError(f"Fichier introuvable : {source.resolve()}")

if N_ROWS < 0:
    raise ValueError("Le nombre de lignes doit etre positif ou nul.")

df0 = pd.read_excel(source)

if df0.empty:
    raise ValueError("Le dataset original est vide.")

print("Dataset original :", source.name)
print("Lignes originales :", len(df0))
print("Colonnes :", list(df0.columns))


# Colonnes communes possibles
C = {
    "id": trouver_colonne(df0, ["id_facture", "id"]),
    "fournisseur": trouver_colonne(df0, ["fournisseur"]),
    "ressource": trouver_colonne(
        df0, ["ressource", "type_ressource", "type_facture"]
    ),
    "foyer": trouver_colonne(df0, ["id_foyer", "foyer"]),
    "gouvernorat": trouver_colonne(df0, ["gouvernorat", "gouvernor"]),
    "superficie": trouver_colonne(
        df0, ["superficie_m2_est", "superficie_m2", "superficie"]
    ),
    "personnes": trouver_colonne(
        df0, ["nb_personnes_est", "nombre_personnes", "nb_personnes"]
    ),
    "date_deb": trouver_colonne(
        df0, ["date_debut", "date_deb", "date_debut_facture"]
    ),
    "date_fin": trouver_colonne(
        df0, ["date_fin", "date_fi", "date_fin_facture"]
    ),
    "nb_mois": trouver_colonne(
        df0, ["nombre_de_mois_facture", "nb_mois", "nombre_mois"]
    ),
    "index_anc": trouver_colonne(
        df0, ["index_ancien", "index_anc", "index_precedent"]
    ),
    "index_nouv": trouver_colonne(
        df0, ["index_nouveau", "index_nouv", "index_actuel"]
    ),
    "conso": trouver_colonne(
        df0, [
            "conso_mensuelle",
            "consommation_mensuelle",
            "consommation_kwh_mensuelle",
            "consommation_m3_par_mois",
            "consommation_kwh_totale",
            "consommation_m3",
            "conso",
            "consommation"
        ]
    ),
    "montant": trouver_colonne(
        df0, [
            "montant_facture_dt",
            "montant_a_payer",
            "montant",
            "montant_facture"
        ]
    )
}

print("\nColonnes detectees :")
for nom, col in C.items():
    print(f"  {nom}: {col}")


# Il faut pouvoir distinguer eau et electricite.
if C["ressource"] is None and C["fournisseur"] is None:
    raise ValueError(
        "Impossible de distinguer SONEDE et STEG : "
        "ajoutez une colonne ressource ou fournisseur."
    )

if C["conso"] is None or C["montant"] is None:
    raise ValueError(
        "Colonnes consommation/montant introuvables. "
        "Adaptez les alias dans le script."
    )


# =========================================================
# 4. SEPARATION SONEDE / STEG
# =========================================================

def selectionner(df, type_ressource):
    if type_ressource == "SONEDE":
        mots_ressource = ["eau", "water", "sonede", "hydrique"]
        mots_fournisseur = ["sonede"]
    else:
        mots_ressource = [
            "electricite", "electrique", "electric", "electricity"
        ]
        mots_fournisseur = ["steg"]

    masque = pd.Series(False, index=df.index)

    if C["ressource"]:
        masque |= texte_normalise(
            df[C["ressource"]]
        ).apply(
            lambda x: any(mot in x for mot in mots_ressource)
        )

    if C["fournisseur"]:
        masque |= texte_normalise(
            df[C["fournisseur"]]
        ).apply(
            lambda x: any(mot in x for mot in mots_fournisseur)
        )

    return df.loc[masque].copy()


# =========================================================
# 5. NETTOYAGE POUR L'APPRENTISSAGE
# =========================================================

def preparer(df):
    d = df.copy()

    d["_conso"] = nombre(d[C["conso"]])
    d["_montant"] = nombre(d[C["montant"]])

    valide = (
        d["_conso"].notna()
        & d["_montant"].notna()
        & (d["_conso"] > 0)
        & (d["_montant"] >= 0)
    )

    if C["personnes"]:
        d["_personnes"] = nombre(d[C["personnes"]])
    else:
        d["_personnes"] = np.nan

    if C["superficie"]:
        d["_superficie"] = nombre(d[C["superficie"]])
    else:
        d["_superficie"] = np.nan

    return d.loc[valide].copy()


# =========================================================
# 6. REGENERATION SONEDE
#    Utilise les index si disponibles.
# =========================================================

def generer_sonede(df, n):
    if n == 0:
        return pd.DataFrame(columns=df0.columns)

    d = preparer(selectionner(df, "SONEDE"))

    if len(d) < 3:
        raise ValueError(
            f"SONEDE : seulement {len(d)} factures valides. "
            "Il faut au moins 3."
        )

    # Sans index, on utilise une generation statistique simple.
    if not C["index_anc"] or not C["index_nouv"]:
        print(
            "Attention : index SONEDE absents. "
            "Generation basee sur consommation et montant."
        )
        return generer_simple(d, n, "SONEDE")

    d["_ia"] = nombre(d[C["index_anc"]])
    d["_in"] = nombre(d[C["index_nouv"]])

    if C["nb_mois"]:
        d["_mois"] = nombre(d[C["nb_mois"]]).fillna(3).clip(lower=1)
    else:
        d["_mois"] = 3

    if C["date_deb"]:
        d["_date"] = pd.to_datetime(d[C["date_deb"]], errors="coerce")
    else:
        d["_date"] = pd.NaT

    d = d.dropna(subset=["_ia", "_in"])
    d["_volume"] = d["_in"] - d["_ia"]
    norm = d[d["_volume"] > 0].copy()

    if len(norm) < 3:
        print("Attention : peu d'index SONEDE coherents.")
        return generer_simple(d, n, "SONEDE")

    norm["_pp"] = (
        norm["_volume"]
        / norm["_mois"]
        / norm["_personnes"].where(norm["_personnes"] > 0, 1)
    )

    if C["date_deb"]:
        norm["_trimestre"] = (
            norm["_date"].dt.month.sub(1).floordiv(3)
        )
        moyenne = norm["_pp"].mean()
        saison = norm.groupby("_trimestre")["_pp"].mean() / moyenne
        saison = saison.replace([np.inf, -np.inf], np.nan).fillna(1)
    else:
        saison = pd.Series(dtype=float)

    facteurs_saison = {
        t: float(np.clip(0.5 + 0.5 * saison.get(t, 1), 0.5, 2))
        for t in range(4)
    }

    # Relation statistique montant-volume.
    x = norm["_volume"].to_numpy(float)
    y = norm["_montant"].to_numpy(float)
    ok = np.isfinite(x) & np.isfinite(y) & (y >= 0)

    coef = np.polyfit(x[ok], y[ok], 1)
    pred = np.maximum(np.polyval(coef, x[ok]), 1)
    residus = np.clip(y[ok] / pred - 1, -0.6, 1.5)

    modeles_foyers = norm.copy()
    profils = norm["_pp"].to_numpy(float)
    profils = profils[np.isfinite(profils) & (profils > 0)]

    if len(profils) == 0:
        profils = np.array([1.0])

    debut_min = norm["_date"].min() if C["date_deb"] else pd.NaT
    debut_max = norm["_date"].max() if C["date_deb"] else pd.NaT

    if pd.isna(debut_min) or pd.isna(debut_max):
        debut_min = pd.Timestamp("2022-01-01")
        debut_max = pd.Timestamp("2025-12-31")

    span = max((debut_max - debut_min).days, 1)

    # Compteurs d'ID synthétiques.
    numero = 1
    if C["foyer"]:
        ids = df[C["foyer"]].astype(str).str.extract(r"(\d+)")[0]
        ids = pd.to_numeric(ids, errors="coerce")
        if ids.notna().any():
            numero = int(ids.max()) + 1

    rows = []

    while len(rows) < n:
        tpl = modeles_foyers.iloc[int(rng.integers(len(modeles_foyers)))]

        personnes = tpl["_personnes"]
        if pd.isna(personnes) or personnes < 1:
            personnes = 1
        personnes = int(round(personnes))

        superficie = tpl["_superficie"]
        if pd.isna(superficie):
            superficie = np.nan

        pp = float(rng.choice(profils) * np.exp(rng.normal(0, 0.25)))

        debut = debut_min + pd.Timedelta(
            days=int(rng.integers(0, span + 1))
        )
        debut = debut.replace(day=1)
        trimestre = (debut.month - 1) // 3

        volume = max(
            1,
            int(round(
                personnes * pp * facteurs_saison[trimestre] * 3
                * rng.normal(1, 0.15)
            ))
        )

        index_ancien = int(rng.choice(norm["_ia"].to_numpy()))
        index_nouveau = index_ancien + volume

        montant = max(
            0,
            float(
                np.polyval(coef, volume)
                * (1 + float(rng.choice(residus)))
            )
        )

        fin = debut + pd.DateOffset(months=3) - pd.Timedelta(days=1)

        row = {c: np.nan for c in df0.columns}

        if C["fournisseur"]:
            row[C["fournisseur"]] = (
                tpl[C["fournisseur"]] if C["fournisseur"] in tpl else "SONEDE"
            )
        if C["ressource"]:
            row[C["ressource"]] = "eau"
        if C["foyer"]:
            row[C["foyer"]] = f"SONEDE_SYN_{numero:06d}"
        if C["gouvernorat"]:
            row[C["gouvernorat"]] = (
                tpl[C["gouvernorat"]] if C["gouvernorat"] in tpl else np.nan
            )
        if C["superficie"]:
            row[C["superficie"]] = superficie
        if C["personnes"]:
            row[C["personnes"]] = personnes
        if C["date_deb"]:
            row[C["date_deb"]] = debut.strftime("%Y-%m-%d")
        if C["date_fin"]:
            row[C["date_fin"]] = fin.strftime("%Y-%m-%d")
        if C["nb_mois"]:
            row[C["nb_mois"]] = 3
        if C["index_anc"]:
            row[C["index_anc"]] = index_ancien
        if C["index_nouv"]:
            row[C["index_nouv"]] = index_nouveau

        row[C["conso"]] = round(volume / 3, 2)
        row[C["montant"]] = round(montant, 2)

        row["origine_donnee"] = "synthetique"
        rows.append(row)
        numero += 1

    return pd.DataFrame(rows)


# =========================================================
# 7. REGENERATION STEG
#    Ne reutilise pas les index SONEDE.
# =========================================================

def generer_simple(d, n, type_ressource):
    if n == 0:
        return pd.DataFrame(columns=df0.columns)

    if len(d) < 3:
        raise ValueError(
            f"{type_ressource} : pas assez de factures valides."
        )

    conso = d["_conso"].to_numpy(float)
    montant = d["_montant"].to_numpy(float)

    # Ajustement statistique montant-consommation.
    ok = np.isfinite(conso) & np.isfinite(montant)
    coef = np.polyfit(conso[ok], montant[ok], 1)

    pred = np.maximum(np.polyval(coef, conso[ok]), 1)
    residus = np.clip(montant[ok] / pred - 1, -0.6, 1.5)

    rows = []

    for i in range(n):
        j = int(rng.integers(len(d)))
        tpl = d.iloc[j]

        nouvelle_conso = max(
            0.01,
            float(tpl["_conso"] * np.exp(rng.normal(0, 0.15)))
        )

        nouveau_montant = max(
            0,
            float(
                np.polyval(coef, nouvelle_conso)
                * (1 + float(rng.choice(residus)))
            )
        )

        row = {c: np.nan for c in df0.columns}

        if C["fournisseur"]:
            row[C["fournisseur"]] = (
                tpl[C["fournisseur"]] if C["fournisseur"] in tpl else type_ressource
            )

        if C["ressource"]:
            row[C["ressource"]] = (
                "eau" if type_ressource == "SONEDE" else "electricite"
            )

        if C["foyer"]:
            row[C["foyer"]] = f"{type_ressource}_SYN_{i + 1:06d}"

        if C["gouvernorat"]:
            row[C["gouvernorat"]] = (
                tpl[C["gouvernorat"]] if C["gouvernorat"] in tpl else np.nan
            )

        if C["superficie"]:
            val = tpl["_superficie"]
            row[C["superficie"]] = val if pd.notna(val) else np.nan

        if C["personnes"]:
            val = tpl["_personnes"]
            row[C["personnes"]] = val if pd.notna(val) else np.nan

        if C["date_deb"]:
            row[C["date_deb"]] = (
                tpl[C["date_deb"]] if C["date_deb"] in tpl else np.nan
            )

        if C["date_fin"]:
            row[C["date_fin"]] = (
                tpl[C["date_fin"]] if C["date_fin"] in tpl else np.nan
            )

        if C["nb_mois"]:
            row[C["nb_mois"]] = 1

        row[C["conso"]] = round(nouvelle_conso, 3)
        row[C["montant"]] = round(nouveau_montant, 2)
        row["origine_donnee"] = "synthetique"

        rows.append(row)

    return pd.DataFrame(rows)


def generer_steg(df, n):
    d = preparer(selectionner(df, "STEG"))

    if len(d) < 3:
        raise ValueError(
            f"STEG : seulement {len(d)} factures valides. "
            "Il faut au moins 3."
        )

    print(
        "\nSTEG : generation statistique a partir de la consommation "
        "et du montant. Les index electriques, s'ils existent, ne sont "
        "pas utilises pour calculer la consommation."
    )

    return generer_simple(d, n, "STEG")


# =========================================================
# 8. LANCER LES DEUX REGENERATIONS
# =========================================================

sonede_original = selectionner(df0, "SONEDE")
steg_original = selectionner(df0, "STEG")

print("\nLignes detectees SONEDE :", len(sonede_original))
print("Lignes detectees STEG :", len(steg_original))

if sonede_original.empty:
    raise ValueError(
        "Aucune ligne SONEDE detectee. Verifiez les valeurs de ressource."
    )

if steg_original.empty:
    raise ValueError(
        "Aucune ligne STEG detectee. Verifiez les valeurs de ressource."
    )

synthetiques_eau = generer_sonede(df0, N_ROWS)
synthetiques_electricite = generer_steg(df0, N_ROWS)

# Les donnees originales sont conservees telles quelles.
original = df0.copy()
original["origine_donnee"] = "reelle"

# Harmoniser les colonnes et combiner les trois groupes.
final = pd.concat(
    [
        original,
        synthetiques_eau,
        synthetiques_electricite
    ],
    ignore_index=True,
    sort=False
)

# Attribuer des IDs uniques uniquement aux nouvelles factures.
if C["id"]:
    masque_synth = final["origine_donnee"].eq("synthetique")
    ids_orig = pd.to_numeric(original[C["id"]], errors="coerce")
    prochain_id = int(ids_orig.max()) + 1 if ids_orig.notna().any() else 1

    nb_synth = int(masque_synth.sum())
    final.loc[masque_synth, C["id"]] = range(
        prochain_id, prochain_id + nb_synth
    )

# Garder les colonnes originales dans leur ordre,
# puis ajouter origine_donnee.
ordre = list(df0.columns)
if "origine_donnee" not in ordre:
    ordre.append("origine_donnee")

final = final.reindex(columns=ordre)

# Export vers un nouveau fichier : ne jamais ecrire dans PATH.
final.to_excel(OUT, sheet_name="dataset_final", index=False)


# =========================================================
# 9. RAPPORT FINAL
# =========================================================

print("\n========== RESULTAT FINAL ==========")
print("Lignes originales conservees :", len(original))
print("Nouvelles lignes SONEDE :", len(synthetiques_eau))
print("Nouvelles lignes STEG :", len(synthetiques_electricite))
print("Total final :", len(final))
print("Fichier cree :", OUT)

print("\nOrigine des donnees :")
print(final["origine_donnee"].value_counts(dropna=False))

if C["ressource"]:
    print("\nRepartition par ressource :")
    print(final[C["ressource"]].value_counts(dropna=False))

print("\nFini. Le dataset original n'a pas ete modifie.")
