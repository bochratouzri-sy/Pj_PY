import pandas as pd, numpy as np
import matplotlib.pyplot as plt, seaborn as sns

sns.set_theme(style="whitegrid")
FICHIER = "dataset_regenere.xlsx"

# ---------- 0. Chargement + préparation ----------
df = pd.read_excel(FICHIER)
df["date_debut"] = pd.to_datetime(df["date_debut"])
df["date_fin"] = pd.to_datetime(df["date_fin"])
df["annee"] = df["date_debut"].dt.year
df["conso_par_pers"] = df["conso_mensuelle"] / df["nb_personnes_est"]
df["conso_par_m2"] = df["conso_mensuelle"] / df["superficie_m2_est"]
df["prix_unitaire"] = df["montant_facture_dt"] / (df["conso_mensuelle"] * df["nb_mois"]).replace(0, np.nan)
df["taille_foyer"] = pd.cut(df["nb_personnes_est"], [0, 2, 4, 8], labels=["1-2 pers", "3-4 pers", "5-8 pers"])
df["classe_surface"] = pd.cut(df["superficie_m2_est"], [0, 120, 200, 400], labels=["<=120 m²", "121-200 m²", ">200 m²"])

# Eau (m³) et électricité (kWh) ont des unités différentes : on les analyse séparément
eau = df[df.ressource == "Eau"].copy()
elec = df[df.ressource == "Electricité"].copy()

# ---------- 1. Indicateurs statistiques ----------
cols = ["conso_mensuelle", "montant_facture_dt", "conso_par_pers", "conso_par_m2"]
for nom, d in [("EAU (SONEDE)", eau), ("ÉLECTRICITÉ (STEG)", elec)]:
    s = d[cols].describe().T
    s["mediane"] = d[cols].median()
    s["cv_%"] = d[cols].std() / d[cols].mean() * 100   # dispersion relative
    s["asymetrie"] = d[cols].skew()
    print(f"\n===== Statistiques : {nom} (n={len(d)}) =====\n", s.round(2))

# ---------- 2. Comparaison selon les profils ----------
for nom, d in [("EAU", eau), ("ÉLEC", elec)]:
    for profil in ["gouvernorat", "taille_foyer", "classe_surface"]:
        t = d.groupby(profil, observed=True).agg(
            n=("id", "count"), conso_moy=("conso_mensuelle", "mean"),
            conso_med=("conso_mensuelle", "median"), par_pers=("conso_par_pers", "mean"),
            facture_moy=("montant_facture_dt", "mean")).round(2)
        print(f"\n--- {nom} par {profil} ---\n", t)

# ---------- 3. Relations entre variables ----------
num = ["superficie_m2_est", "nb_personnes_est", "conso_mensuelle", "montant_facture_dt"]
corr_eau = eau[num].corr(method="spearman")
print("\nCorrélations (Spearman) - EAU\n", corr_eau.round(2))
if len(elec) > 5:
    print("\nCorrélations (Spearman) - ÉLEC\n", elec[num].corr(method="spearman").round(2))

# ---------- 4. Consommations inhabituelles ----------
def outliers_iqr(d, col="conso_mensuelle"):
    q1, q3 = d[col].quantile([.25, .75])
    return (d[col] < q1 - 1.5 * (q3 - q1)) | (d[col] > q3 + 1.5 * (q3 - q1))

eau["anomalie"] = eau.groupby("gouvernorat")["conso_mensuelle"].transform(
    lambda x: (x - x.mean()).abs() / x.std() > 3) | outliers_iqr(eau)
elec["anomalie"] = outliers_iqr(elec) if len(elec) else False
anom = pd.concat([eau[eau.anomalie], elec[elec.anomalie]])
print(f"\nConsommations inhabituelles : {len(anom)} lignes "
      f"({len(anom) / len(df):.1%} du dataset)")
print(anom.sort_values("conso_mensuelle", ascending=False)[
    ["id", "ressource", "foyer_ref", "gouvernorat", "nb_personnes_est",
     "conso_mensuelle", "montant_facture_dt"]].head(10).to_string(index=False))

# Anomalies de qualité des données
print("\nContrôle qualité :")
print(" - conso = 0            :", (df.conso_mensuelle == 0).sum())
print(" - dates futures (>auj.):", (df.date_debut > pd.Timestamp.today()).sum())
print(" - périodes != 3 mois   :", (df.nb_mois != 3).sum())

# ---------- 5. Visualisation ----------
fig, ax = plt.subplots(2, 3, figsize=(18, 10))
sns.histplot(eau.conso_mensuelle, bins=40, kde=True, ax=ax[0, 0]).set(title="Distribution conso eau (m³/mois)")
sns.boxplot(data=eau, x="gouvernorat", y="conso_mensuelle", ax=ax[0, 1]).set(title="Eau par gouvernorat")
sns.barplot(data=eau, x="taille_foyer", y="conso_mensuelle", errorbar=None, ax=ax[0, 2]).set(title="Eau selon taille du foyer")
sns.heatmap(corr_eau, annot=True, cmap="coolwarm", vmin=-1, vmax=1, ax=ax[1, 0]).set(title="Corrélations (eau)")
sns.scatterplot(data=eau, x="conso_mensuelle", y="montant_facture_dt", hue="anomalie",
                palette={False: "steelblue", True: "red"}, ax=ax[1, 1]).set(title="Consommation vs facture (anomalies en rouge)")
sns.lineplot(data=eau[eau.annee.between(2015, 2026)], x="annee", y="conso_mensuelle", marker="o", ax=ax[1, 2]).set(title="Évolution annuelle conso eau")
plt.tight_layout()
plt.savefig("etape2_visualisation.png", dpi=150)
plt.show()
