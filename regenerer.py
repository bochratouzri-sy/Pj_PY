"""
Régénération / augmentation du dataset SONEDE.

Usage :
  python regenerer_local.py dataset_nettoye.xlsx 1000              -> 1000 NOUVELLES lignes
  python regenerer_local.py dataset_nettoye.xlsx 1000 --avec-original -> original + 1000 nouvelles lignes
  (argument 2 facultatif : nombre de lignes, 500 par défaut)
"""
import sys
import numpy as np
import pandas as pd

# ============ 0. PARAMETRES ============
PATH = sys.argv[1] if len(sys.argv) > 1 else "dataset.xlsx"
N_ROWS = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 500
AVEC_ORIGINAL = "--avec-original" in sys.argv
SEED = 42
rng = np.random.default_rng(SEED)

# ============ 1. LECTURE + DETECTION DES COLONNES ============
df0 = pd.read_excel(PATH)

def col(prefix):
    for c in df0.columns:
        if str(c).strip().lower().startswith(prefix):
            return c
    raise KeyError(f"Colonne introuvable : {prefix}")

K = ["id", "fournisseur", "ressource", "foyer", "gouvernor", "superficie", "nb_personnes",
     "date_deb", "date_fi", "nb_mois", "index_anc", "index_nouv", "conso", "montant"]
C = {k: col(k) for k in K}

def to_num(s):
    return pd.to_numeric(s.astype(str).str.replace(",", ".").str.replace(" ", ""), errors="coerce")

df = df0.copy()
for k in ["superficie", "nb_personnes", "nb_mois", "index_anc", "index_nouv", "conso", "montant"]:
    df[C[k]] = to_num(df[C[k]])
for k in ["date_deb", "date_fi"]:
    df[C[k]] = pd.to_datetime(df[C[k]], errors="coerce")
df = df.dropna(subset=[C["index_anc"], C["index_nouv"], C["date_deb"], C["nb_personnes"]]).reset_index(drop=True)
print(f"Fichier lu : {len(df)} lignes exploitables -> génération de {N_ROWS} nouvelles lignes")

# ============ 2. APPRENTISSAGE ============
vol = df[C["index_nouv"]] - df[C["index_anc"]]
anom = vol <= 0                                         # factures estimées (index inchangés)
norm = df[~anom].copy()
nbm = norm[C["nb_mois"]].fillna(3)
norm["conso_pp"] = (vol[~anom] / nbm) / norm[C["nb_personnes"]]
norm["trim"] = (norm[C["date_deb"]].dt.month - 1) // 3

# a) saisonnalité (lissée)
sais = norm.groupby("trim")["conso_pp"].mean() / norm["conso_pp"].mean()
SAISON = {t: 0.5 * float(sais.get(t, 1.0)) + 0.5 for t in range(4)}

# b) niveau de conso par foyer (empirique -> reproduit la vraie dispersion)
FOYER_PP = norm.groupby(C["foyer"])["conso_pp"].median()
ALL_PP = norm["conso_pp"].values

# c) tarif : montant ~ a + b*volume, résidus relatifs ré-échantillonnés (bootstrap)
x = vol[~anom].values.astype(float)
y = norm[C["montant"]].values.astype(float)
ok = ~np.isnan(y) & (y < np.nanpercentile(y, 98))
COEF = np.polyfit(x[ok], y[ok], 1)
pred = np.polyval(COEF, x[ok])
RES = np.clip(y[ok] / np.maximum(pred, 1) - 1, -0.6, 1.5)
MONT_MIN = float(np.nanmin(y))

# d) foyers modèles (gouvernorat, superficie, personnes, nb de factures propre)
FOY = df.groupby(C["foyer"]).agg(
    gouv=(C["gouvernor"], "first"), sup=(C["superficie"], "first"),
    nbp=(C["nb_personnes"], "first"), n=(C["foyer"], "size")).reset_index()
P_FIRST = float((df[C["date_deb"]].dt.day == 1).mean())
D_MIN, D_MAX = df[C["date_deb"]].min(), df[C["date_deb"]].max()
INDEX_STARTS = df[C["index_anc"]].values
P_ANOM = float(anom.mean())
ANOM_ROWS = df[anom]
FOURN = df[C["fournisseur"]].mode()[0]
RESS = df[C["ressource"]].mode()[0]

nums = pd.to_numeric(df[C["foyer"]].astype(str).str.extract(r"(\d+)")[0], errors="coerce")
N_F = int(nums.max()) if nums.notna().any() else 0       # les nouveaux foyers continuent la numérotation

# ============ 3. GENERATION ============
rows = []
span_days = max((D_MAX - D_MIN).days, 1)
while len(rows) < N_ROWS:
    N_F += 1
    tpl = FOY.iloc[int(rng.integers(len(FOY)))]
    nbp = int(tpl["nbp"])
    base_pp = FOYER_PP.get(tpl[C["foyer"]], np.median(ALL_PP))
    conso_pp = float(base_pp * np.exp(rng.normal(0, 0.25)))       # même profil, léger écart
    index = int(rng.choice(INDEX_STARTS))
    first_style = rng.random() < P_FIRST
    debut = D_MIN + pd.Timedelta(days=int(rng.integers(0, span_days)))
    debut = debut.replace(day=1) if first_style else debut + pd.offsets.MonthEnd(0)

    for _ in range(int(tpl["n"])):
        if len(rows) >= N_ROWS:
            break
        fin = (debut + pd.DateOffset(months=3) - pd.Timedelta(days=1)) if first_style \
            else debut + pd.DateOffset(months=3)

        if len(ANOM_ROWS) and rng.random() < P_ANOM:             # facture estimée
            a = ANOM_ROWS.iloc[int(rng.integers(len(ANOM_ROWS)))]
            nouveau, conso_m, mont = index, a[C["conso"]], a[C["montant"]]
        else:
            c_m = max(0.0, nbp * conso_pp * SAISON[(debut.month - 1) // 3] * rng.normal(1, 0.15))
            v = int(round(c_m * 3))
            nouveau = index + v
            conso_m = round(v / 3, 2)
            mont = round(max(np.polyval(COEF, v) * (1 + rng.choice(RES)), MONT_MIN), 1)

        rows.append({
            C["fournisseur"]: FOURN, C["ressource"]: RESS, C["foyer"]: f"F{N_F:02d}",
            C["gouvernor"]: tpl["gouv"], C["superficie"]: tpl["sup"], C["nb_personnes"]: nbp,
            C["date_deb"]: debut.strftime("%Y-%m-%d"), C["date_fi"]: fin.strftime("%Y-%m-%d"),
            C["nb_mois"]: 3, C["index_anc"]: index, C["index_nouv"]: nouveau,
            C["conso"]: conso_m, C["montant"]: mont,
        })
        index = nouveau
        debut = fin + pd.Timedelta(days=1) if first_style else fin

new = pd.DataFrame(rows)
cols = [c for c in df0.columns if c in new.columns]

if AVEC_ORIGINAL:
    orig = df.copy()
    for k in ["date_deb", "date_fi"]:
        orig[C[k]] = orig[C[k]].dt.strftime("%Y-%m-%d")
    final = pd.concat([orig[cols], new[cols]], ignore_index=True)
else:
    final = new[cols].copy()
final[C["id"]] = range(1, len(final) + 1)
final = final[[c for c in df0.columns if c in final.columns]]

# ============ 4. VALIDATION ============
v_new = new[C["index_nouv"]] - new[C["index_anc"]]
n_ok = new[v_new > 0]
assert ((v_new[v_new > 0] / 3).round(2) - n_ok[C["conso"]]).abs().max() < 0.01, "conso incohérente"
print("Contrôles OK\n")
rep = []
for k in ["superficie", "nb_personnes", "conso", "montant"]:
    a, b = df[C[k]].dropna(), new[C[k]].dropna()
    rep.append({"colonne": C[k], "moy_orig": a.mean(), "moy_new": b.mean(),
                "med_orig": a.median(), "med_new": b.median(),
                "std_orig": a.std(), "std_new": b.std()})
print(pd.DataFrame(rep).round(2).to_string(index=False))
print("\nGouvernorats (orig vs new) :")
print(pd.concat([df[C["gouvernor"]].value_counts(normalize=True).rename("orig"),
                 new[C["gouvernor"]].value_counts(normalize=True).rename("new")], axis=1).round(3))

# ============ 5. EXPORT ============
OUT = "dataset_regenere.xlsx"
final.to_excel(OUT, sheet_name="dataset", index=False)
print(f"\nFichier créé : {OUT} -> {len(final)} lignes")
