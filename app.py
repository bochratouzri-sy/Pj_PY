"""
Interface web (Streamlit).   Lancement :  streamlit run app.py

Aucune logique de modèle ici : tout vient de
  donnees.py (données), fonctions.py (fonction1/2/3), collecte.py (enregistrement).
"""
import io
import os
import unicodedata

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.ticker import MaxNLocator
import streamlit as st

st.set_page_config(page_title="Suivi de consommation", page_icon="💧", layout="wide")

from donnees import D, GOUV, UNITE, df as DF_PROPRE
from fonctions import fonction1, fonction2, fonction3, MOIS
from collecte import ajouter_foyer, FOURNISSEUR, FICHIER_SAISIES, dossier_utilisateur

RESSOURCES = list(D.keys())                     # ["Eau", "Electricité"]
DEFAUTS = {"Eau": dict(ancien=1000.0, actuel=1040.0, prec="40"), "Electricité": dict(ancien=5000.0, actuel=5240.0, prec="360")}
          

# Palette 
BLEU = "#17365D"       
ACCENT = "#2874A6"      # couleur principale (boutons, cartes)
VERT, ORANGE, BRUN = "#1e8e3e", "#d97706", "#b45309"
# Une couleur par graphique 
C_GOUV, C_PERS, C_SURF, C_MOIS, C_HIST, C_FACT = "#2874A6", "#1e8e3e", "#d97706", "#7e57c2", "#00897b", "#17365D"
COULEUR_NIVEAU = {"économe": VERT, "normal": VERT, "élevé": ORANGE, "gros consommateur": BRUN}
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Style : 

st.markdown(f"""
<style>
#MainMenu, footer {{visibility: hidden;}}
.block-container {{padding-top: 1.5rem; max-width: 1100px;}}
.bandeau {{background: {BLEU}; color: white; padding: 22px 16px; border-radius: 12px;text-align: center; margin-bottom: 14px;}}
.bandeau h1 {{color: white; margin: 0; padding: 0; font-size: 2rem;}}
.bandeau p {{color: white; opacity: .85; margin: 4px 0 0 0;}}
.carte {{border: 1px solid rgba(128,128,128,.3); border-left: 5px solid {ACCENT}; border-radius: 12px;
        padding: 16px 18px; background: rgba(128,128,128,.07); height: 100%;}}
.carte .t {{font-size: .85rem; opacity: .75; margin-bottom: 4px;}}
.carte .v {{font-size: 1.7rem; font-weight: 700; line-height: 1.2;}}
.carte .s {{font-size: .85rem; opacity: .75; margin-top: 4px;}}
.badge {{display: inline-block; padding: 3px 12px; border-radius: 999px; color: white; font-weight: 600;}}
.alerte {{border-left: 5px solid; border-radius: 6px; padding: 10px 14px; margin: 8px 0;
         background: rgba(128,128,128,.07);}}
.phrase {{font-size: 1.1rem; margin: 6px 0 14px 0;}}
</style>""", unsafe_allow_html=True)


def carte(titre, valeur, sous=""):
    st.markdown(f'<div class="carte"><div class="t">{titre}</div><div class="v">{valeur}</div>'
                f'<div class="s">{sous}</div></div>', unsafe_allow_html=True)


def en_xlsx(tableau, feuille="Donnees"):
    """DataFrame -> contenu d'un fichier Excel (.xlsx) prêt à télécharger."""
    tampon = io.BytesIO()
    with pd.ExcelWriter(tampon, engine="openpyxl") as ecrivain:
        tableau.to_excel(ecrivain, index=False, sheet_name=feuille)
    return tampon.getvalue()


def normaliser_ressource(txt):
    t = unicodedata.normalize("NFD", str(txt)).encode("ascii", "ignore").decode().strip().lower()
    return {"eau": "Eau", "electricite": "Electricité"}.get(t)



# Analyse d'un foyer 

def analyser(r, gouv, pers, surface, ancien, actuel, jours, mois, precedente=None):
    if jours <= 0:
        raise ValueError("Le nombre de jours doit être supérieur à zéro.")
    if actuel < ancien:
        raise ValueError("L'index actuel doit être supérieur ou égal à l'index ancien.")
    if pers <= 0 or surface <= 0:
        raise ValueError("Le nombre de personnes et la surface doivent être positifs.")
    if precedente is not None and precedente < 0:
        raise ValueError("La consommation précédente ne peut pas être négative.")
    r1 = fonction1(r, ancien, actuel, jours)
    conso_mensuelle = round(r1["conso_projetee_periode"] / 3, 1)
    r2 = fonction2(r, pers, surface, gouv, conso_mensuelle)
    precedente_mensuelle = (precedente / 3 if precedente is not None else None)
    r3 = fonction3(r, pers, surface, gouv, conso_mensuelle, mois, precedente_mensuelle)
    return {"r": r, "gouv": gouv, "pers": pers, "surface": surface, "r1": r1, "r2": r2, "r3": r3,
            "ancien": ancien, "actuel": actuel, "jours": jours}


def afficher_resultats(res, cle="saisie"):
    r, u = res["r"], UNITE[res["r"]]
    r1, r2, r3 = res["r1"], res["r2"], res["r3"]
    niveau = r2["niveau"]

    st.markdown(f"### Résultats : {r} ({FOURNISSEUR.get(r, '')}), {res['gouv']}, "
                f"{res['pers']} pers., {res['surface']} m²")

    # 1. Où j'en suis ?
    st.markdown("#### 1. Où j'en suis ?")
    st.markdown(f'<div class="phrase">À ce rythme, vous consommerez <b>{r1["conso_projetee_periode"]} {u}</b> '
                f'sur 3 mois et paierez environ <b>{r1["facture_estimee_DT"]} DT</b>.</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        carte("Consommation projetée", f"{r1['conso_projetee_periode']} {u}", "sur 3 mois")
    with c2:
        carte("Facture estimée", f"{r1['facture_estimee_DT']} DT", "sur 3 mois")
    with c3:
        carte("Économie si -10 %", f"{r1['economie_si_-10%_DT']} DT", "en réduisant votre consommation")

    # 2. Est-ce que je consomme normalement ?
    st.markdown("#### 2. Est-ce que je consomme normalement ?")
    couleur = COULEUR_NIVEAU.get(niveau, ACCENT)
    st.markdown(f'Les foyers semblables consomment <b>{r2["foyers_semblables"]} {u}/mois</b>, '
                f'vous <b>{r2["ma_conso"]} {u}/mois</b> : <span class="badge" style="background:{couleur}">'
                f'{niveau}</span>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        carte("Foyers semblables", f"{r2['foyers_semblables']} {u}", "par mois")
    with c2:
        carte("Vous", f"{r2['ma_conso']} {u}", "par mois")
    with c3:
        carte("Objectif", f"{r2['objectif']} {u}", "par mois")

    # 3. Dois-je faire attention ?
    st.markdown("#### 3. Dois-je faire attention ?")
    for a in r3:
        if "Anomalie" in a or "Rupture" in a:
            c = BRUN
        elif "Pic" in a:
            c = ORANGE
        else:
            c = VERT
        st.markdown(f'<div class="alerte" style="border-color:{c}">{a.strip()}</div>', unsafe_allow_html=True)

    # Simulateur d'économie : réutilise uniquement fonction1 avec une consommation réduite
    st.markdown("#### Simulateur d'économie")
    pct = st.slider("Et si je réduis ma consommation de :", 0, 50, 10, step=5, format="%d %%", key=f"sim_{cle}")
    reduit = fonction1(r, res["ancien"], res["ancien"] + (res["actuel"] - res["ancien"]) * (1 - pct / 100),
                       res["jours"])
    eco = round(r1["facture_estimee_DT"] - reduit["facture_estimee_DT"], 1)
    c1, c2, c3 = st.columns(3)
    with c1:
        carte(f"Consommation avec -{pct} %", f"{reduit['conso_projetee_periode']} {u}", "sur 3 mois")
    with c2:
        carte("Nouvelle facture estimée", f"{reduit['facture_estimee_DT']} DT", "sur 3 mois")
    with c3:
        carte("Économie", f"{eco} DT", f"soit environ {round(eco * 4, 1)} DT par an")


# En-tête + navigation par onglets 

st.markdown("""
<div class="bandeau">
  <h1>Suivi de consommation</h1>
  <p>Eau et électricité · Estimation · Comparaison · Alertes</p>
</div>""", unsafe_allow_html=True)

onglet_analyse, onglet_dash, onglet_historique = st.tabs(
    ["Mon analyse", "Tableau de bord", "Historique"])

COLONNES_IMPORT = ["ressource", "gouvernorat", "nb_personnes", "superficie_m2", "index_ancien",
                   "index_actuel", "jours_ecoules", "mois_actuel", "conso_precedente"]


# ONGLET 1 : MON ANALYSE

with onglet_analyse:
    c1, c2 = st.columns(2)
    mode = c1.radio("Données du foyer", ["Saisir", "Importer un fichier"], horizontal=True)

    # ---------------- saisie manuelle ----------------
    if mode == "Saisir":
        r = c2.radio("Ressource", RESSOURCES, horizontal=True,
                     format_func=lambda x: f"{x} ({FOURNISSEUR.get(x, '')})")
        d = DEFAUTS.get(r, DEFAUTS["Eau"])
        with st.form("formulaire"):
            c1, c2, c3 = st.columns(3)
            gouv = c1.selectbox("Gouvernorat", GOUV)
            pers = c2.number_input("Nombre de personnes", min_value=1, max_value=15, value=4, step=1)
            surface = c3.number_input("Surface (m²)", min_value=20, max_value=500, value=150, step=10)
            c1, c2, c3 = st.columns(3)
            ancien = c1.number_input("Index ancien (compteur)", value=d["ancien"], key=f"anc_{r}")
            actuel = c2.number_input("Index actuel (compteur)", value=d["actuel"], key=f"act_{r}")
            jours = c3.number_input("Jours écoulés", min_value=1, max_value=180, value=60, step=1)
            c1, c2 = st.columns(2)
            mois = c1.selectbox("Mois actuel", list(range(1, 13)), index=7,
                                format_func=lambda i: MOIS[i - 1].capitalize())
            prec_txt = c2.text_input("Consommation de la période précédente (facultatif)",
                                     value=d["prec"], key=f"prec_{r}")
            enregistrer = st.checkbox("Enregistrer ce foyer dans l'historique", value=True)
            envoye = st.form_submit_button("Calculer ma consommation", type="primary")

        if envoye:
            try:
                precedente = float(prec_txt.replace(",", ".")) if prec_txt.strip() != "" else None
                st.session_state["resultat"] = analyser(r, gouv, int(pers), float(surface), ancien, actuel,
                                                        int(jours), mois, precedente)
                if enregistrer:
                    ajouter_foyer(r, gouv, int(pers), surface, ancien, actuel, int(jours), mois)
            except ValueError as e:
                st.session_state.pop("resultat", None)
                st.error(f"Erreur : {e}")

        if "resultat" in st.session_state:
            st.divider()
            afficher_resultats(st.session_state["resultat"])

    # ---------------- import d'un fichier ----------------
    else:
        st.write("Importez un fichier Excel ou CSV (un foyer par ligne) avec les colonnes : "
                 + ", ".join(f"`{c}`" for c in COLONNES_IMPORT) + " (`conso_precedente` est facultative).")
        modele = pd.DataFrame([
            ["Eau", GOUV[0], 4, 150, 1000, 1040, 60, 8, 40],
            ["Electricité", GOUV[0], 4, 150, 5000, 5240, 60, 8, 360]], columns=COLONNES_IMPORT)
        st.download_button("Télécharger le modèle de fichier (Excel)", en_xlsx(modele, "Modele"),
                           file_name="modele_import.xlsx", mime=XLSX)
        fichier = st.file_uploader("Votre fichier", type=["xlsx", "csv"])
        if fichier is not None:
            try:
                if fichier.name.lower().endswith(".csv"):
                    brut = pd.read_csv(io.BytesIO(fichier.getvalue()), sep=None, engine="python")
                else:
                    brut = pd.read_excel(io.BytesIO(fichier.getvalue()))
                brut.columns = [str(c).strip().lower() for c in brut.columns]
                manquantes = [c for c in COLONNES_IMPORT[:-1] if c not in brut.columns]
                if manquantes:
                    st.error(f"Colonnes manquantes : {manquantes}")
                else:
                    lignes, details = [], {}
                    for i, row in brut.iterrows():
                        try:
                            ress = normaliser_ressource(row["ressource"])
                            if ress is None:
                                raise ValueError("Ressource inconnue (Eau ou Electricité).")
                            if row["gouvernorat"] not in GOUV:
                                raise ValueError(f"Gouvernorat inconnu. Choisissez parmi : {GOUV}")
                            prec = row.get("conso_precedente", np.nan)
                            prec = None if pd.isna(prec) else float(str(prec).replace(",", "."))
                            res = analyser(ress, row["gouvernorat"], int(row["nb_personnes"]),
                                           float(row["superficie_m2"]), float(row["index_ancien"]),
                                           float(row["index_actuel"]), int(row["jours_ecoules"]),
                                           int(row["mois_actuel"]), prec)
                            details[i + 1] = res
                            u = UNITE[ress]
                            lignes.append({"Foyer": i + 1, "Ressource": ress, "Gouvernorat": row["gouvernorat"],
                                           "Conso projetée (3 mois)": f"{res['r1']['conso_projetee_periode']} {u}",
                                           "Facture estimée (DT)": res["r1"]["facture_estimee_DT"],
                                           "Niveau": res["r2"]["niveau"],
                                           "Alertes": " | ".join(a.strip() for a in res["r3"]), "Erreur": ""})
                        except Exception as e:
                            lignes.append({"Foyer": i + 1, "Ressource": row.get("ressource", ""),
                                           "Gouvernorat": row.get("gouvernorat", ""), "Erreur": str(e)})
                    tableau = pd.DataFrame(lignes).fillna("")
                    st.dataframe(tableau, hide_index=True)
                    st.download_button("Télécharger les résultats (Excel)", en_xlsx(tableau, "Resultats"),
                                       file_name="resultats_foyers.xlsx", mime=XLSX)
                    if details:
                        st.divider()
                        choix = st.selectbox("Voir le détail d'un foyer", list(details.keys()))
                        afficher_resultats(details[choix], cle="import")
            except Exception as e:
                st.error(f"Impossible de lire le fichier : {e}")



# ONGLET 2 : TABLEAU DE BORD
COUL_RES = {"Eau": ACCENT, "Electricité": ORANGE}
MOYENNE = dict(marker="D", markerfacecolor="white", markeredgecolor=BRUN, markersize=5)


def fr(x, d=1):
    """Nombre avec virgule décimale (12.5 -> '12,5')."""
    return f"{x:.{d}f}".replace(".", ",")


def iqr_out(s, k=1.5):
    """True pour les valeurs hors de [Q1 - k*IQR ; Q3 + k*IQR]."""
    q1, q3 = s.quantile([.25, .75])
    return (s < q1 - k * (q3 - q1)) | (s > q3 + k * (q3 - q1))


def zrob(s):
    """z-score robuste (basé sur la médiane)."""
    return 0.6745 * (s - s.median()) / np.median(np.abs(s - s.median()))


@st.cache_data
def preparer_analyse():
    """Ajoute les colonnes d'analyse aux données propres et repère les consommations inhabituelles."""
    df = DF_PROPRE.copy()
    df["conso_totale"] = df["conso_periode"]
    df["conso_par_personne"] = df["conso_mensuelle"] / df["nb_personnes_est"]
    df["prix_unitaire"] = df["montant_facture_dt"] / df["conso_totale"]
    df["date_milieu"] = df["date_debut"] + (df["date_fin"] - df["date_debut"]) / 2
    df["saison"] = df["mois"].map(lambda m: "Hiver" if m in (12, 1, 2) else "Printemps" if m in (3, 4, 5)
                                  else "Eté" if m in (6, 7, 8) else "Automne")
    df["taille_foyer"] = pd.cut(df["nb_personnes_est"], [0, 2, 4, np.inf], labels=["1-2 pers.", "3-4 pers.", "5+ pers."])
    df["surface"] = pd.cut(df["superficie_m2_est"], [0, 120, 200, np.inf], labels=["<120 m²", "120-200", ">200 m²"])
    groupes = {r: df[df["ressource"] == r].copy() for r in RESSOURCES}
    for g in groupes.values():
        g["anomalie"] = (iqr_out(g["conso_mensuelle"]) | (zrob(g["conso_mensuelle"]).abs() > 3.5)
                         | iqr_out(g["conso_par_personne"]))
    return groupes


def panneau():
    """Cadre arrondi autour d'un élément (aspect « carte » d'un tableau de bord)."""
    try:
        return st.container(border=True)
    except TypeError:                          # ancienne version de Streamlit
        return st.container()


def montrer(fig):
    """Affiche une figure matplotlib dans un panneau, puis la ferme."""
    with panneau():
        st.pyplot(fig)
    plt.close(fig)


# --- graphiques
def fig_ligne(serie, titre, ylabel, couleur):
    fig, a = plt.subplots(figsize=(5.4, 3.4))
    a.plot(serie.index, serie.values, marker="o", color=couleur)
    a.set(title=titre, ylabel=ylabel)
    a.xaxis.set_major_locator(MaxNLocator(integer=True))
    fig.tight_layout()
    return fig


def fig_distribution(d, nom, u):
    fig, a = plt.subplots(figsize=(5.4, 3.4))
    s = d["conso_mensuelle"]
    sns.histplot(s, kde=s.nunique() > 1, color=COUL_RES[nom], ax=a)
    a.axvline(s.mean(), color=BRUN, ls="--", label=f"moyenne = {fr(s.mean())}")
    a.axvline(s.median(), color=VERT, ls="--", label=f"médiane = {fr(s.median())}")
    a.set(title="Distribution de la consommation", xlabel=f"{u}/mois", ylabel="Effectif")
    a.legend(fontsize=8)
    fig.tight_layout()
    return fig


def fig_top10(d, u):
    fig, a = plt.subplots(figsize=(5.4, 3.4))
    top = d.groupby("foyer_ref").conso_mensuelle.mean().nlargest(10).sort_values()
    a.barh(top.index.astype(str), top.values, color=C_HIST)
    a.set(title="10 plus gros consommateurs", xlabel=f"{u}/mois")
    fig.tight_layout()
    return fig


def fig_comparaison(compare):
    fig, a = plt.subplots(figsize=(5.4, 3.4))
    a.bar(list(compare.keys()), list(compare.values()), color=[COUL_RES[n] for n in compare])
    a.set(title="Facture moyenne par mois : eau et électricité", ylabel="DT/mois")
    fig.tight_layout()
    return fig


def tableau_indicateurs(d, u):
    """Indicateurs statistiques de la consommation mensuelle."""
    s = d["conso_mensuelle"]
    lignes = [("Relevés", fr(len(s), 0)), ("Moyenne", fr(s.mean())), ("Médiane", fr(s.median())),
              ("Ecart-type", fr(s.std())), ("CV (%)", fr(s.std() / s.mean() * 100)), ("Minimum", fr(s.min())),
              ("1er quartile", fr(s.quantile(.25))), ("3e quartile", fr(s.quantile(.75))), ("Maximum", fr(s.max()))]
    return pd.DataFrame(lignes, columns=["Indicateur", f"Valeur ({u}/mois)"])


def boite(a, src, x, ordre, titre, couleur, ylabel=""):
    """Boîte à moustaches de la consommation selon une catégorie (◆ = moyenne)."""
    a.set_title(titre)
    if src.empty:
        a.text(0.5, 0.5, "Pas de données", ha="center", va="center", transform=a.transAxes)
        a.set_xticks([]); a.set_yticks([])
        return
    sns.boxplot(data=src, x=x, y="conso_mensuelle", order=ordre, color=couleur, ax=a,
                showmeans=True, meanprops=MOYENNE, fliersize=2.5, linewidth=.9)
    a.set(xlabel="", ylabel=ylabel)
    a.tick_params(axis="x", labelsize=8)


def fig_profils(d, nom, u):
    nb = d["gouvernorat"].value_counts()
    nom_g = {g: f"{g}\n(n={nb[g]})" for g in nb.index}              # le nombre de relevés est affiché sous le nom
    d = d.assign(gouv_n=d["gouvernorat"].map(nom_g))
    fig, ax = plt.subplots(2, 2, figsize=(11, 6.8))
    c = COUL_RES[nom]
    boite(ax[0, 0], d, "gouv_n", [nom_g[g] for g in sorted(nb.index)], "Par gouvernorat", c, f"{u}/mois")
    boite(ax[0, 1], d, "taille_foyer", None, "Par taille du foyer", c)
    boite(ax[1, 0], d, "surface", None, "Par surface", c, f"{u}/mois")
    boite(ax[1, 1], d[d["nb_mois"] <= 4], "saison", ["Hiver", "Printemps", "Eté", "Automne"], "Par saison", c)
    fig.tight_layout()
    return fig


def fig_relations(d, nom, u):
    noms = {"superficie_m2_est": "Superf.", "nb_personnes_est": "Nb pers.",
            "conso_mensuelle": "Conso", "montant_facture_dt": "Facture"}
    fig, ax = plt.subplots(2, 2, figsize=(11, 7))
    corr = d[list(noms)].rank().corr().rename(index=noms, columns=noms)          # corrélation de Spearman
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="BrBG", vmin=-1, vmax=1, cbar=False,
                annot_kws={"size": 9}, ax=ax[0, 0])
    ax[0, 0].set_title("Corrélations (Spearman)")
    nuages = [(ax[0, 1], "nb_personnes_est", "conso_mensuelle", "Nb personnes", f"{u}/mois", "Consommation selon le nombre de personnes"),
              (ax[1, 0], "superficie_m2_est", "conso_mensuelle", "Superficie (m²)", f"{u}/mois", "Consommation selon la superficie"),
              (ax[1, 1], "conso_totale", "montant_facture_dt", f"Consommation de la période ({u})", "Facture (DT)", "Facture selon la consommation")]
    for a, x, y, xl, yl, tt in nuages:
        try:
            sns.regplot(data=d, x=x, y=y, x_jitter=0.15 if x == "nb_personnes_est" else 0, color=COUL_RES[nom],
                        scatter_kws={"alpha": .3, "s": 9}, line_kws={"color": BRUN, "lw": 1.5}, ax=a)
            a.set(title=f"{tt}\nR² = {fr(np.corrcoef(d[x], d[y])[0, 1] ** 2, 2)}", xlabel=xl, ylabel=yl)
        except Exception:                                                   # ex. : une seule valeur après filtrage
            a.set(title=tt)
            a.text(0.5, 0.5, "Pas assez de variation", ha="center", va="center", transform=a.transAxes)
        a.title.set_fontsize(10)
    fig.tight_layout()
    return fig


def fig_anomalies(d, nom, u):
    fig, a = plt.subplots(figsize=(6.4, 4.2))
    normal, inhab = d[~d["anomalie"]], d[d["anomalie"]]
    a.scatter(normal["date_milieu"], normal["conso_mensuelle"], s=10, alpha=.4, color=COUL_RES[nom], label="normal")
    a.scatter(inhab["date_milieu"], inhab["conso_mensuelle"], s=45, color=BRUN, edgecolor="k",
              label=f"inhabituel : {len(inhab)} ({fr(len(inhab) / len(d) * 100)} %)")
    a.set(title="Consommations dans le temps", ylabel=f"{u}/mois")
    a.legend(fontsize=8)
    a.tick_params(axis="x", rotation=30)            # dates lisibles
    fig.tight_layout()
    return fig


# ------------ page
def tableau_de_bord(GR):
    # ---- barre de filtres  ----
    with panneau():
        c1, c2, c3, c4 = st.columns(4)
        r = c1.radio("Ressource", RESSOURCES, key="dash_ress", horizontal=True,
             format_func=lambda x: f"{x} ({FOURNISSEUR.get(x, '')})")
        base, u = GR[r], UNITE[r]
        a_min, a_max = int(base.date_debut.dt.year.min()), int(base.date_debut.dt.year.max())
        p_min, p_max = int(base.nb_personnes_est.min()), int(base.nb_personnes_est.max())
        gouvs = c2.multiselect("Gouvernorat", GOUV, default=GOUV, key="dash_gouv")
        periode = c3.slider("Période (années)", a_min, a_max, (a_min, a_max), key=f"dash_per_{r}") if a_min < a_max else (a_min, a_max)
        nb_pers = c4.slider("Nombre de personnes", p_min, p_max, (p_min, p_max), key=f"dash_pers_{r}") if p_min < p_max else (p_min, p_max)

    def filtrer(donnees):
        return donnees[donnees.gouvernorat.isin(gouvs)
                       & donnees.date_debut.dt.year.between(*periode)
                       & donnees.nb_personnes_est.between(*nb_pers)]

    d = filtrer(base)
    if d.empty:
        st.warning("Aucune donnée pour ces filtres.")
        return
    if len(d) < 5:
        st.info("Pas assez de relevés pour ces filtres : élargissez la sélection.")
        return
    d = d.assign(annee=d.date_debut.dt.year, facture_mois=d.montant_facture_dt / d.nb_mois)

    # ---- chiffres clés ----
    prix = d.montant_facture_dt.sum() / d.conso_periode.sum()
    nb_inhab = int(d.anomalie.sum())
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        carte("Consommation moyenne", f"{d.conso_mensuelle.mean():.1f} {u}", "par mois")
    with k2:
        carte("Facture moyenne", f"{d.facture_mois.mean():.1f} DT", "par mois")
    with k3:
        carte("Prix moyen", f"{prix:.3f} DT", f"par {u}")
    with k4:
        carte("Foyers", d.foyer_ref.nunique(), f"{len(d)} relevés")
    with k5:
        carte("Inhabituelles", nb_inhab, f"{nb_inhab / len(d) * 100:.1f} % des relevés")
    st.write("")

    t_apercu, t_profils, t_relations, t_inhab = st.tabs(["Aperçu", "Profils", "Relations", "Inhabituelles"])

    with t_apercu:
        g1, g2 = st.columns(2)
        with g1:
            montrer(fig_ligne(d.groupby("annee").conso_mensuelle.mean(), "Consommation moyenne par année",f"{u}/mois", C_GOUV))                     
        with g2:
            montrer(fig_ligne(d.groupby("annee").facture_mois.mean(), "Facture moyenne par mois, par année","DT/mois", C_PERS))                
        g1, g2 = st.columns(2)
        with g1:
            montrer(fig_distribution(d, r, u))
        with g2:
            montrer(fig_top10(d, u))
        g1, g2 = st.columns(2)
        with g1:
            compare = {nom: (f.montant_facture_dt / f.nb_mois).mean() for nom, donnees in GR.items()
                       for f in [filtrer(donnees)] if len(f)}
            montrer(fig_comparaison(compare))
        with g2:
            with panneau():
                st.dataframe(tableau_indicateurs(d, u), hide_index=True, height=330)

    with t_profils:
        montrer(fig_profils(d, r, u))

    with t_relations:
        montrer(fig_relations(d, r, u))

    with t_inhab:
        g1, g2 = st.columns([3, 2])
        with g1:
            montrer(fig_anomalies(d, r, u))
        liste = (d[d.anomalie].sort_values("conso_mensuelle", ascending=False)
                 [["foyer_ref", "gouvernorat", "nb_personnes_est", "date_debut", "conso_mensuelle"]]
                 .rename(columns={"foyer_ref": "Foyer", "gouvernorat": "Gouvernorat", "nb_personnes_est": "Personnes",
                                  "date_debut": "Début", "conso_mensuelle": f"Conso ({u}/mois)"}))
        liste["Début"] = liste["Début"].dt.strftime("%m/%Y")
        with g2:
            with panneau():
                if len(liste):
                    st.dataframe(liste, hide_index=True, height=330)
                    st.download_button("Télécharger la liste (CSV)", liste.to_csv(index=False, sep=";").encode("utf-8-sig"),
                                       file_name="consommations_inhabituelles.csv", mime="text/csv")
                else:
                    st.info("Aucune consommation inhabituelle pour ces filtres.")

with onglet_dash:
    with sns.axes_style("whitegrid"):
        tableau_de_bord(preparer_analyse())


# ONGLET 3 : HISTORIQUE (foyers enregistrés par collecte.py)

with onglet_historique:
    chemin = os.path.join(dossier_utilisateur(), FICHIER_SAISIES)
    if os.path.exists(chemin):
        saisies = pd.read_csv(chemin)
        st.write(f"{len(saisies)} foyer(s) enregistré(s).")
        st.dataframe(saisies, hide_index=True)
        st.download_button("Télécharger l'historique (Excel)", en_xlsx(saisies, "Historique"),
                           file_name="foyers_saisis.xlsx", mime=XLSX)
    else:
        st.info("Aucun foyer enregistré pour le moment. Faites une analyse dans « Mon analyse ».")