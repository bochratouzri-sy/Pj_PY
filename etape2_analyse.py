# -*- coding: utf-8 -*-
"""
Etape 2 - Analyse et visualisation des donnees : TABLEAU DE BORD UNIQUE (une seule fenetre)
Bibliotheques : pandas, numpy, matplotlib, seaborn, openpyxl   (pas de scipy / sklearn)
Lancer : python etape2_dashboard.py    (dataset_regenere.xlsx dans le meme dossier)

Le tableau de bord contient, de haut en bas :
  1) Indicateurs statistiques   2) Comparaison selon les profils
  3) Relations entre variables  4) Consommations inhabituelles
  5) Validation 2 : principales observations (texte genere automatiquement)
"""
import textwrap
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

FICHIER = "dataset_regenere.xlsx"
SORTIE = "tableau_de_bord_etape2.png"
sns.set_theme(style="whitegrid", font_scale=0.8)
COUL = {"Eau": "#1f77b4", "Electricité": "#ff7f0e"}
UNITE = {"Eau": "m³/mois", "Electricité": "kWh/mois"}
fr = lambda x, d=1: f"{x:.{d}f}".replace(".", ",")          # virgule decimale

# ============================================================ DONNEES
df = pd.read_excel(FICHIER, sheet_name="Donnees", parse_dates=["date_debut", "date_fin"])
df["conso_totale"] = df["conso_mensuelle"] * df["nb_mois"]
df["conso_par_personne"] = df["conso_mensuelle"] / df["nb_personnes_est"]
df["prix_unitaire"] = df["montant_facture_dt"] / df["conso_totale"]
df["date_milieu"] = df["date_debut"] + (df["date_fin"] - df["date_debut"]) / 2
df["mois"] = df["date_milieu"].dt.month
df["saison"] = df["mois"].map(lambda m: "Hiver" if m in (12, 1, 2) else "Printemps" if m in (3, 4, 5)
                              else "Eté" if m in (6, 7, 8) else "Automne")
df["taille_foyer"] = pd.cut(df["nb_personnes_est"], [0, 2, 4, 8], labels=["1-2 pers.", "3-4 pers.", "5-8 pers."])
df["surface"] = pd.cut(df["superficie_m2_est"], [0, 120, 200, 400], labels=["<120 m²", "120-200", ">200 m²"])
GR = {r: df[df["ressource"] == r].copy() for r in ["Eau", "Electricité"]}


# ---- anomalies : IQR ou z-score robuste sur la conso, ou IQR sur la conso par personne
def iqr_out(s, k=1.5):
    q1, q3 = s.quantile([.25, .75])
    return (s < q1 - k * (q3 - q1)) | (s > q3 + k * (q3 - q1))


def zrob(s):
    return 0.6745 * (s - s.median()) / np.median(np.abs(s - s.median()))


for g in GR.values():
    g["anomalie"] = (iqr_out(g["conso_mensuelle"]) | (zrob(g["conso_mensuelle"]).abs() > 3.5)
                     | iqr_out(g["conso_par_personne"]))
pd.concat(GR.values()).query("anomalie").sort_values(["ressource", "conso_mensuelle"], ascending=[True, False]) \
    .to_csv("anomalies.csv", index=False, encoding="utf-8-sig", sep=";")

# ============================================================ FIGURE UNIQUE
fig = plt.figure(figsize=(24, 16), layout="constrained")
sf = fig.subfigures(5, 1, height_ratios=[1, 1, 1, 1.05, 0.8], hspace=0.02)
TIT = dict(x=0.005, ha="left", fontsize=13, fontweight="bold", color="#1a3d6d")

# ------------------------------------------------ 1) INDICATEURS STATISTIQUES
sf[0].suptitle("1) Indicateurs statistiques", **TIT)
ax = sf[0].subplots(1, 3, gridspec_kw={"width_ratios": [1, 1, 1.1]})
for a, (nom, g) in zip(ax[:2], GR.items()):
    s = g["conso_mensuelle"]
    sns.histplot(s, kde=True, color=COUL[nom], ax=a)
    a.axvline(s.mean(), color="red", ls="--", label=f"moyenne = {fr(s.mean())}")
    a.axvline(s.median(), color="green", ls="--", label=f"médiane = {fr(s.median())}")
    a.set(title=f"{nom} : distribution de la consommation", xlabel=UNITE[nom], ylabel="Effectif")
    a.legend(fontsize=8)
st = pd.DataFrame({n: g["conso_mensuelle"] for n, g in GR.items()})
tab = pd.DataFrame({
    "N": st.count(), "Moyenne": st.mean(), "Médiane": st.median(), "Ecart-type": st.std(),
    "CV (%)": st.std() / st.mean() * 100, "Min": st.min(), "Q1": st.quantile(.25),
    "Q3": st.quantile(.75), "Max": st.max()}).T
ax[2].axis("off")
tb = ax[2].table(cellText=[[fr(v) for v in r] for r in tab.values], rowLabels=tab.index,
                 colLabels=["Eau (m³/mois)", "Electricité (kWh/mois)"], loc="center", cellLoc="center")
tb.auto_set_font_size(False); tb.set_fontsize(10); tb.scale(1, 1.55)
ax[2].set_title("Statistiques descriptives (consommation mensuelle)")

# ------------------------------------------------ 2) PROFILS
sf[1].suptitle("2) Comparaison des consommations selon les profils (◆ = moyenne)", **TIT)
ax = sf[1].subplots(1, 8)
mp = dict(marker="D", markerfacecolor="white", markeredgecolor="red", markersize=5)
k = 0
for nom, g in GR.items():
    profils = [(g[g["gouvernorat"].isin(["Ariana", "Nabeul"])], "gouvernorat", None, "Gouvernorat"),
               (g, "taille_foyer", None, "Taille du foyer"),
               (g, "surface", None, "Surface"),
               (g[g["nb_mois"] <= 4], "saison", ["Hiver", "Printemps", "Eté", "Automne"], "Saison")]
    for src, col, ordre, tit in profils:
        a = ax[k]; k += 1
        sns.boxplot(data=src, x=col, y="conso_mensuelle", order=ordre, color=COUL[nom], ax=a,
                    showmeans=True, meanprops=mp, fliersize=2.5, linewidth=.9)
        a.set(title=f"{nom} - {tit}", xlabel="", ylabel=UNITE[nom] if tit == "Gouvernorat" else "")
        a.tick_params(axis="x", rotation=25, labelsize=8)

# ------------------------------------------------ 3) RELATIONS
sf[2].suptitle("3) Relations entre les variables", **TIT)
ax = sf[2].subplots(1, 8, gridspec_kw={"width_ratios": [1.25, 1, 1, 1, 1.25, 1, 1, 1]})
VARS = {"superficie_m2_est": "Superf.", "nb_personnes_est": "Nb pers.",
        "conso_mensuelle": "Conso", "montant_facture_dt": "Facture"}
k = 0
for nom, g in GR.items():
    a = ax[k]; k += 1
    corr = g[list(VARS)].rank().corr().rename(index=VARS, columns=VARS)     # Spearman
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm", vmin=-1, vmax=1, cbar=False,
                annot_kws={"size": 8}, ax=a)
    a.set_title(f"{nom} : corrélations (Spearman)"); a.tick_params(labelsize=8)
    for x, y, xl, yl, tt in [("nb_personnes_est", "conso_mensuelle", "Nb personnes", UNITE[nom], "Conso vs personnes"),
                             ("superficie_m2_est", "conso_mensuelle", "Superficie (m²)", "", "Conso vs superficie"),
                             ("conso_totale", "montant_facture_dt", "Conso totale", "Facture (DT)", "Facture vs conso")]:
        a = ax[k]; k += 1
        sns.regplot(data=g, x=x, y=y, x_jitter=0.15 if x == "nb_personnes_est" else 0, color=COUL[nom],
                    scatter_kws={"alpha": .3, "s": 9}, line_kws={"color": "red", "lw": 1.5}, ax=a)
        r2 = np.corrcoef(g[x], g[y])[0, 1] ** 2
        a.set(title=f"{nom[:4]}. : {tt}\nR² = {fr(r2, 2)}", xlabel=xl, ylabel=yl)
        a.title.set_fontsize(9)

# ------------------------------------------------ 4) ANOMALIES
sf[3].suptitle("4) Identification des consommations inhabituelles", **TIT)
ax = sf[3].subplots(1, 4, gridspec_kw={"width_ratios": [2, 1.2, 2, 1.2]})
for i, (nom, g) in enumerate(GR.items()):
    n, an = g[~g["anomalie"]], g[g["anomalie"]]
    a = ax[2 * i]
    a.scatter(n["date_milieu"], n["conso_mensuelle"], s=10, alpha=.4, color=COUL[nom], label="normal")
    a.scatter(an["date_milieu"], an["conso_mensuelle"], s=45, color="red", edgecolor="k",
              label=f"inhabituel : {len(an)} ({fr(len(an) / len(g) * 100)} %)")
    a.set(title=f"{nom} : consommations dans le temps", ylabel=UNITE[nom]); a.legend(fontsize=8)
    a = ax[2 * i + 1]
    top = an.nlargest(10, "conso_mensuelle").iloc[::-1]
    a.barh(top["foyer_ref"] + " (" + top["date_debut"].dt.strftime("%m/%Y") + ")", top["conso_mensuelle"], color="red")
    a.axvline(g["conso_mensuelle"].median(), color="green", ls="--", label="médiane")
    a.set(title=f"{nom} : top 10", xlabel=UNITE[nom]); a.legend(fontsize=8); a.tick_params(axis="y", labelsize=8)

# ------------------------------------------------ 5) VALIDATION 2 : OBSERVATIONS
sf[4].suptitle("Validation 2 : principales observations", **TIT)
ax = sf[4].subplots(1, 1); ax.axis("off")
E, L = GR["Eau"], GR["Electricité"]
m = lambda g, c, col="conso_mensuelle": g.groupby(c, observed=True)[col].mean()
rho = lambda g, c: g[[c, "conso_mensuelle"]].rank().corr().iloc[0, 1]
ecart_gv = {n: abs(np.diff(m(g[g.gouvernorat.isin(["Ariana", "Nabeul"])], "gouvernorat").values)[0])
               / g["conso_mensuelle"].mean() * 100 for n, g in GR.items()}
sais = {n: m(g[g.nb_mois <= 4], "saison") for n, g in GR.items()}
qu = {n: g.groupby(pd.qcut(g["conso_mensuelle"], 4), observed=True)["prix_unitaire"].mean().values for n, g in GR.items()}
pp = m(L, "taille_foyer", "conso_par_personne")
topE, topL = E[E.anomalie].nlargest(1, "conso_mensuelle").iloc[0], L[L.anomalie].nlargest(1, "conso_mensuelle").iloc[0]
obs = [
    f"Niveaux : consommation moyenne de {fr(E.conso_mensuelle.mean())} m³/mois pour l'eau (médiane {fr(E.conso_mensuelle.median())}) "
    f"et {fr(L.conso_mensuelle.mean())} kWh/mois pour l'électricité (médiane {fr(L.conso_mensuelle.median())}) ; "
    f"distributions asymétriques (CV = {fr(E.conso_mensuelle.std() / E.conso_mensuelle.mean() * 100, 0)} % et "
    f"{fr(L.conso_mensuelle.std() / L.conso_mensuelle.mean() * 100, 0)} %).",
    f"Taille du foyer : facteur le plus discriminant. Eau {fr(m(E, 'taille_foyer').iloc[0])} → {fr(m(E, 'taille_foyer').iloc[-1])} m³ "
    f"et électricité {fr(m(L, 'taille_foyer').iloc[0], 0)} → {fr(m(L, 'taille_foyer').iloc[-1], 0)} kWh (petit → grand foyer). "
    f"Par personne, l'électricité baisse de {fr(pp.iloc[0], 0)} à {fr(pp.iloc[-1], 0)} kWh (économies d'échelle).",
    f"Gouvernorat : écart Ariana / Nabeul de {fr(ecart_gv['Eau'])} % (eau) et {fr(ecart_gv['Electricité'])} % (électricité) "
    f"→ pas de différence notable (Sousse : trop peu de relevés).",
    f"Saison : pic en {sais['Eau'].idxmax()} pour l'eau ({fr(sais['Eau'].max())} m³ vs {fr(sais['Eau'].min())} en {sais['Eau'].idxmin()}) "
    f"et en {sais['Electricité'].idxmax()} pour l'électricité ({fr(sais['Electricité'].max(), 0)} vs {fr(sais['Electricité'].min(), 0)} kWh en {sais['Electricité'].idxmin()}).",
    f"Relations : la consommation dépend surtout du nombre de personnes (Spearman = {fr(rho(E, 'nb_personnes_est'), 2)} eau ; "
    f"{fr(rho(L, 'nb_personnes_est'), 2)} électricité) et moins de la superficie ({fr(rho(E, 'superficie_m2_est'), 2)} ; {fr(rho(L, 'superficie_m2_est'), 2)}). "
    f"La facture suit la consommation (quasi linéaire).",
    f"Tarification : prix unitaire de l'électricité de {fr(qu['Electricité'][0], 2)} à {fr(qu['Electricité'][-1], 2)} DT/kWh selon la tranche "
    f"(tarif progressif) ; eau {fr(qu['Eau'][0], 2)} → {fr(qu['Eau'][-1], 2)} DT/m³.",
    f"Consommations inhabituelles : {int(E.anomalie.sum())} relevés d'eau ({fr(E.anomalie.mean() * 100)} %) et {int(L.anomalie.sum())} d'électricité "
    f"({fr(L.anomalie.mean() * 100)} %). Maximums : foyer {topE.foyer_ref} ({fr(topE.conso_mensuelle)} m³/mois) et foyer {topL.foyer_ref} "
    f"({fr(topL.conso_mensuelle, 0)} kWh/mois). Liste complète dans anomalies.csv.",
]
for col, bloc in enumerate([obs[:4], obs[4:]]):
    txt = "\n".join("• " + textwrap.fill(o, 118, subsequent_indent="   ") for o in bloc)
    ax.text(0.005 + col * 0.505, 0.97, txt, va="top", ha="left", fontsize=10.5, linespacing=1.5,
            transform=ax.transAxes)

# ============================================================ SORTIE
fig.savefig(SORTIE, dpi=110)
print(f"Tableau de bord enregistré : {SORTIE}  |  anomalies : anomalies.csv")
try:                                      # ouvrir la fenetre en plein ecran (Windows)
    plt.get_current_fig_manager().window.state("zoomed")
except Exception:
    pass
plt.show()                                # UNE SEULE fenetre
