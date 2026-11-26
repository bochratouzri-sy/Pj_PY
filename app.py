"""Interface web (Streamlit).   Lancement :  streamlit run app.py

Aucune logique de modèle ici : donnees.py (données), fonctions.py (fonction1/2/3), collecte.py (enregistrement).
"""
import io
import os
import unicodedata

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import streamlit as st

st.set_page_config(page_title="Suivi de consommation", page_icon="logo.png", layout="wide")

from donnees import D, GOUV, UNITE
from fonctions import fonction1, fonction2, fonction3, MOIS
from collecte import ajouter_foyer, FOURNISSEUR, FICHIER_SAISIES, dossier_utilisateur

RESSOURCES = list(D.keys())                     # ["Eau", "Electricité"]
DEFAUTS = {"Eau": dict(ancien=1000.0, actuel=1040.0, prec=""),
           "Electricité": dict(ancien=5000.0, actuel=5240.0, prec="")}
BLEU, ACCENT = "#17365D", "#2874A6"
VERT, ORANGE, BRUN = "#1e8e3e", "#d97706", "#b45309"
COULEUR_NIVEAU = {"économe": VERT, "normal": VERT, "élevé": ORANGE, "gros consommateur": BRUN}
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
OBLIGATOIRES = ["ressource", "gouvernorat", "nb_personnes", "superficie_m2", "index_ancien", "index_actuel"]
FACULTATIVES = ["nb_mois", "date_debut", "date_fin", "jours_ecoules", "mois_actuel", "conso_precedente", "budget"]

st.markdown(f"""
<style>
#MainMenu, footer {{visibility: hidden;}}
.block-container {{padding-top: 1.5rem; max-width: 1100px;}}
.bandeau {{background: {BLEU}; color: white; padding: 22px 16px; border-radius: 12px; text-align: center; margin-bottom: 14px;}}
.bandeau h1 {{color: white; margin: 0; padding: 0; font-size: 2rem;}}
.bandeau p {{color: white; opacity: .85; margin: 4px 0 0 0;}}
.carte {{border: 1px solid rgba(128,128,128,.3); border-left: 5px solid {ACCENT}; border-radius: 12px;
        padding: 16px 18px; background: rgba(128,128,128,.07); height: 100%;}}
.carte .t {{font-size: .85rem; opacity: .75; margin-bottom: 4px;}}
.carte .v {{font-size: 1.7rem; font-weight: 700; line-height: 1.2;}}
.carte .s {{font-size: .85rem; opacity: .75; margin-top: 4px;}}
.badge {{display: inline-block; padding: 3px 12px; border-radius: 999px; color: white; font-weight: 600;}}
.alerte {{border-left: 5px solid; border-radius: 6px; padding: 10px 14px; margin: 8px 0; background: rgba(128,128,128,.07);}}
.phrase {{font-size: 1.1rem; margin: 6px 0 14px 0;}}
</style>""", unsafe_allow_html=True)


def cartes(*items):
    """Affiche des cartes côte à côte : chaque élément = (titre, valeur, sous-titre)."""
    for col, (titre, valeur, sous) in zip(st.columns(len(items)), items):
        col.markdown(f'<div class="carte"><div class="t">{titre}</div><div class="v">{valeur}</div>'
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


def valeur(row, nom):
    """Valeur d'une colonne facultative, ou None si la colonne est absente ou la cellule vide."""
    v = row.get(nom, np.nan)
    return None if pd.isna(v) else v


def analyser(r, gouv, pers, surface, ancien, actuel, jours, mois, precedente=None, nb_mois=3, budget=None):
    """Vérifie les saisies puis appelle les fonctions du projet (1 : facture, 2 : normal + alertes, 4 : budget)."""
    for erreur, message in [(jours <= 0, "Le nombre de jours doit être supérieur à zéro."),
                            (actuel < ancien, "L'index actuel doit être supérieur ou égal à l'index ancien."),
                            (pers <= 0 or surface <= 0, "Le nombre de personnes et la surface doivent être positifs."),
                            (precedente is not None and precedente < 0, "La consommation précédente ne peut pas être négative."),
                            (budget is not None and budget <= 0, "Le budget doit être supérieur à zéro.")]:
        if erreur:
            raise ValueError(message)
    r1 = fonction1(r, ancien, actuel, jours, nb_mois)
    conso_mensuelle = round(r1["conso_projetee_periode"] / nb_mois, 1)
    r2 = fonction2(r, pers, surface, gouv, conso_mensuelle, precedente / nb_mois if precedente is not None else None, nb_mois)
    r4 = fonction3(r, budget, r1["conso_projetee_periode"], nb_mois) if budget is not None else None
    return {"r": r, "gouv": gouv, "pers": pers, "surface": surface, "r1": r1, "r2": r2, "r4": r4,
            "ancien": ancien, "actuel": actuel, "jours": jours, "mois": mois, "nb_mois": nb_mois}


MOIS_COURT = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]


def historique_foyer(r, gouv, pers, surface, exclure=None):
    """Analyses déjà enregistrées pour ce foyer (même ressource, gouvernorat, nombre de personnes et surface).
    `exclure` = (index_ancien, index_actuel, jours, mois) de l'analyse en cours, pour ne pas la compter deux fois."""
    chemin = os.path.join(dossier_utilisateur(), FICHIER_SAISIES)
    if not os.path.exists(chemin):
        return pd.DataFrame(columns=["mois", "conso_mensuelle"])
    try:
        h = pd.read_csv(chemin)
    except (PermissionError, pd.errors.EmptyDataError):
        return pd.DataFrame(columns=["mois", "conso_mensuelle"])
    h = h[(h.ressource == r) & (h.gouvernorat == gouv) & (h.nb_personnes == pers) & (h.superficie_m2 == surface)]
    h = h.drop_duplicates(["index_ancien", "index_actuel", "jours_ecoules", "mois"], keep="last")
    if exclure is not None:
        h = h[~((h.index_ancien == exclure[0]) & (h.index_actuel == exclure[1])
                & (h.jours_ecoules == exclure[2]) & (h.mois == exclure[3]))]
    return h.assign(conso_mensuelle=(h.index_actuel - h.index_ancien) / h.jours_ecoules * 30)


def graphique_historique(res):
    """Consommation du foyer mois par mois : analyses précédentes enregistrées + analyse actuelle."""
    r, u = res["r"], UNITE[res["r"]]
    h = historique_foyer(r, res["gouv"], res["pers"], res["surface"],
                         exclure=(res["ancien"], res["actuel"], res["jours"], res["mois"])).tail(7)
    noms = [MOIS_COURT[int(m) - 1] for m in h.mois] + ["Maintenant"]
    valeurs = list(h.conso_mensuelle) + [res["r2"]["ma_conso"]]
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.bar(range(len(valeurs)), valeurs, color=[ACCENT] * (len(valeurs) - 1) + [ORANGE])
    ax.axhline(res["r2"]["foyers_semblables"], color="gray", linestyle="--", linewidth=1.5)
    ax.set_xticks(range(len(valeurs)), noms)
    ax.set_ylabel(f"{u} par mois")
    ax.set_ylim(0, max(valeurs + [res["r2"]["foyers_semblables"]]) * 1.35)
    ax.set_title("Votre consommation, mois par mois", fontsize=11)
    ax.legend(handles=[Patch(color=ACCENT, label="Mois précédents"), Patch(color=ORANGE, label="Maintenant"),
                       Line2D([0], [0], color="gray", linestyle="--", label="Foyers semblables")],
              fontsize=8, frameon=False, loc="upper left", ncol=3)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)
    if len(h) == 0:
        st.caption("Première analyse de ce foyer : vos mois précédents apparaîtront ici à chaque nouvelle analyse enregistrée.")


def afficher_resultats(res, cle="saisie"):
    r, u, nm = res["r"], UNITE[res["r"]], res["nb_mois"]
    r1, r2, r4 = res["r1"], res["r2"], res["r4"]
    fourchette = f"entre {r1['facture_min_DT']} et {r1['facture_max_DT']} DT"

    st.markdown(f"### Résultats : {r} ({FOURNISSEUR.get(r, '')}), {res['gouv']}, {res['pers']} pers., {res['surface']} m²")

    st.markdown("#### 1. Où j'en suis ?")
    st.markdown(f'<div class="phrase">À ce rythme, vous consommerez <b>{r1["conso_projetee_periode"]} {u}</b> '
                f'sur {nm} mois et paierez environ <b>{r1["facture_estimee_DT"]} DT</b> ({fourchette}).</div>',
                unsafe_allow_html=True)
    cartes(("Consommation projetée", f"{r1['conso_projetee_periode']} {u}", f"sur {nm} mois"),
           ("Facture estimée", f"{r1['facture_estimee_DT']} DT", fourchette),
           ("Économie si -10 %", f"{r1['economie_si_-10%_DT']} DT", "en réduisant votre consommation"))

    st.markdown("#### 2. Est-ce que je consomme normalement ?")
    couleur = COULEUR_NIVEAU.get(r2["niveau"], ACCENT)
    st.markdown(f'Les foyers semblables consomment <b>{r2["foyers_semblables"]} {u}/mois</b>, '
                f'vous <b>{r2["ma_conso"]} {u}/mois</b> : <span class="badge" style="background:{couleur}">'
                f'{r2["niveau"]}</span>', unsafe_allow_html=True)
    cartes(("Foyers semblables", f"{r2['foyers_semblables']} {u}", "par mois"),
           ("Vous", f"{r2['ma_conso']} {u}", "par mois"),
           ("Objectif", f"{r2['objectif']} {u}", "par mois"))

    for a in r2["alertes"]:
        c = BRUN if a.strip().startswith("Attention") else ORANGE if a.strip().startswith("Économie") else VERT
        st.markdown(f'<div class="alerte" style="border-color:{c}">{a.strip()}</div>', unsafe_allow_html=True)
    graphique_historique(res)

    if r4:
        st.markdown("#### 3. Mon budget")
        cartes(("Votre budget", f"{r4['budget']:g} DT", f"sur {nm} mois"),
               ("Facture estimée", f"{r4['facture']} DT", fourchette),
               ("Dépassement" if r4["depasse"] else "Il vous reste", f"{r4['ecart_DT']} DT",
                "à réduire" if r4["depasse"] else "sous votre budget"))
        st.markdown(f'<div class="alerte" style="border-color:{BRUN if r4["depasse"] else VERT}">{r4["message"]}</div>',
                    unsafe_allow_html=True)

    st.markdown("#### Simulateur d'économie")
    pct = st.slider("Et si je réduis ma consommation de :", 0, 50, 10, step=5, format="%d %%", key=f"sim_{cle}")
    reduit = fonction1(r, res["ancien"], res["ancien"] + (res["actuel"] - res["ancien"]) * (1 - pct / 100),
                       res["jours"], nm)
    eco = round(r1["facture_estimee_DT"] - reduit["facture_estimee_DT"], 1)
    cartes((f"Consommation avec -{pct} %", f"{reduit['conso_projetee_periode']} {u}", f"sur {nm} mois"),
           ("Nouvelle facture estimée", f"{reduit['facture_estimee_DT']} DT", f"sur {nm} mois"),
           ("Économie", f"{eco} DT", f"soit environ {round(eco * 12 / nm, 1)} DT par an"))


def analyser_ligne(row):
    """Analyse une ligne du fichier importé (jours et mois déduits des dates si les colonnes manquent)."""
    ress = normaliser_ressource(row["ressource"])
    if ress is None:
        raise ValueError("Ressource inconnue (Eau ou Electricité).")
    if row["gouvernorat"] not in GOUV:
        raise ValueError(f"Gouvernorat inconnu. Choisissez parmi : {GOUV}")
    prec = valeur(row, "conso_precedente")
    budget = valeur(row, "budget")
    nb_m = int(valeur(row, "nb_mois") or 3)
    debut, fin = (pd.to_datetime(valeur(row, c), errors="coerce") for c in ("date_debut", "date_fin"))
    dates_ok = not (pd.isna(debut) or pd.isna(fin))
    jours = valeur(row, "jours_ecoules")
    jours = int(jours) if jours is not None else ((fin - debut).days if dates_ok else nb_m * 30)
    mois = valeur(row, "mois_actuel")
    mois = int(mois) if mois is not None else ((debut + (fin - debut) / 2).month if dates_ok else pd.Timestamp.today().month)
    return analyser(ress, row["gouvernorat"], int(row["nb_personnes"]), float(row["superficie_m2"]),
                    float(row["index_ancien"]), float(row["index_actuel"]), jours, mois,
                    None if prec is None else float(str(prec).replace(",", ".")), nb_m,
                    None if budget is None else float(str(budget).replace(",", ".")))


# ===================== Page =====================
st.markdown("""
<div class="bandeau">
  <h1>Suivi de consommation</h1>
  <p>Eau et électricité · Estimation · Comparaison · Alertes · Budget</p>
</div>""", unsafe_allow_html=True)

onglet_analyse, onglet_historique = st.tabs(["Mon analyse", "Historique"])

with onglet_analyse:
    c1, c2 = st.columns(2)
    mode = c1.radio("Données du foyer", ["Saisir", "Importer un fichier"], horizontal=True)

    if mode == "Saisir":
        r = c2.radio("Ressource", RESSOURCES, horizontal=True, format_func=lambda x: f"{x} ({FOURNISSEUR.get(x, '')})")
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
            mois = c1.selectbox("Mois actuel", list(range(1, 13)), index=7, format_func=lambda i: MOIS[i - 1].capitalize())
            prec_txt = c2.text_input("Consommation de la période précédente (facultatif)", value=d["prec"], key=f"prec_{r}",
                                     help="Laissez vide : l'application utilise votre dernière analyse enregistrée.")
            nb_mois = st.selectbox("Durée de la période facturée (mois)", [1, 2, 3, 4, 6],
                                   index=2 if r == "Eau" else 1, key=f"nm_{r}")
            budget_txt = st.text_input("Budget maximum pour cette période, en DT (facultatif)", key=f"budget_{r}",
                                       help="Exemple : 60. L'application dit si vous le dépasserez et de combien réduire votre consommation.")
            enregistrer = st.checkbox("Enregistrer ce foyer dans l'historique", value=True)
            envoye = st.form_submit_button("Calculer ma consommation", type="primary")

        if envoye:
            try:
                try:
                    budget = float(budget_txt.replace(",", ".")) if budget_txt.strip() != "" else None
                except ValueError:
                    raise ValueError("Le budget doit être un nombre (exemple : 60).")
                precedente = float(prec_txt.replace(",", ".")) if prec_txt.strip() != "" else None
                if precedente is None:                       # champ vide : on reprend la dernière analyse enregistrée
                    avant = historique_foyer(r, gouv, int(pers), surface, exclure=(ancien, actuel, int(jours), mois))
                    if len(avant):
                        precedente = avant.conso_mensuelle.iloc[-1] * int(nb_mois)
                st.session_state["resultat"] = analyser(r, gouv, int(pers), float(surface), ancien, actuel,
                                                        int(jours), mois, precedente, int(nb_mois), budget)
                if enregistrer and len(historique_foyer(r, gouv, int(pers), surface)) == len(
                        historique_foyer(r, gouv, int(pers), surface, exclure=(ancien, actuel, int(jours), mois))):
                    try:
                        ajouter_foyer(r, gouv, int(pers), surface, ancien, actuel, int(jours), mois)   # pas de doublon
                    except PermissionError:
                        st.warning("Le calcul est fait, mais l'historique n'a pas pu être enregistré : le fichier "
                                   f"{FICHIER_SAISIES} est probablement ouvert dans Excel. Fermez-le puis recalculez.")
            except ValueError as e:
                st.session_state.pop("resultat", None)
                st.error(f"Erreur : {e}")

        if "resultat" in st.session_state:
            st.divider()
            afficher_resultats(st.session_state["resultat"])

    else:
        st.write("Importez un fichier Excel ou CSV (un foyer par ligne) avec les colonnes : "
                 + ", ".join(f"`{c}`" for c in OBLIGATOIRES) + ". Facultatives : " + ", ".join(f"`{c}`" for c in FACULTATIVES) + ".")
        modele = pd.DataFrame([["Eau", GOUV[0], 4, 150, 1000, 1040, 3, "2025-08-01", "2025-10-31"],
                               ["Electricité", GOUV[0], 4, 150, 5000, 5240, 2, "2025-08-01", "2025-09-30"]],
                              columns=OBLIGATOIRES + ["nb_mois", "date_debut", "date_fin"])
        st.download_button("Télécharger le modèle de fichier (Excel)", en_xlsx(modele, "Modele"),
                           file_name="modele_import.xlsx", mime=XLSX)
        fichier = st.file_uploader("Votre fichier", type=["xlsx", "csv"])
        if fichier is not None:
            try:
                contenu = io.BytesIO(fichier.getvalue())
                brut = pd.read_csv(contenu, sep=None, engine="python") if fichier.name.lower().endswith(".csv") \
                    else pd.read_excel(contenu)
                brut.columns = [str(c).strip().lower() for c in brut.columns]
                if "index_nouveau" in brut.columns and "index_actuel" not in brut.columns:
                    brut = brut.rename(columns={"index_nouveau": "index_actuel"})
                manquantes = [c for c in OBLIGATOIRES if c not in brut.columns]
                if manquantes:
                    st.error(f"Colonnes manquantes : {manquantes}")
                else:
                    lignes, details = [], {}
                    for i, row in brut.iterrows():
                        try:
                            res = analyser_ligne(row)
                            details[i + 1] = res
                            lignes.append({"Foyer": i + 1, "Ressource": res["r"], "Gouvernorat": res["gouv"],
                                           "Conso projetée (période)": f"{res['r1']['conso_projetee_periode']} {UNITE[res['r']]} / {res['nb_mois']} mois",
                                           "Facture estimée (DT)": res["r1"]["facture_estimee_DT"],
                                           "Niveau": res["r2"]["niveau"],
                                           "Alertes": " | ".join("Tout va bien" if "Tout va bien" in a else a.strip() for a in res["r2"]["alertes"]),
                                           "Budget": res["r4"]["resume"] if res["r4"] else "",
                                           "Erreur": ""})
                        except Exception as e:
                            lignes.append({"Foyer": i + 1, "Ressource": row.get("ressource", ""),
                                           "Gouvernorat": row.get("gouvernorat", ""), "Erreur": str(e)})
                    tableau = pd.DataFrame(lignes).fillna("")
                    st.dataframe(tableau, hide_index=True)
                    total = sum(x["r1"]["facture_estimee_DT"] for x in details.values())
                    st.markdown(f"**Total estimé pour {len(details)} foyer(s) : {round(total, 1)} DT**")
                    st.download_button("Télécharger les résultats (Excel)", en_xlsx(tableau, "Resultats"),
                                       file_name="resultats_foyers.xlsx", mime=XLSX)
                    if details:
                        st.divider()
                        choix = st.selectbox("Voir le détail d'un foyer", list(details.keys()))
                        afficher_resultats(details[choix], cle="import")
            except Exception as e:
                st.error(f"Impossible de lire le fichier : {e}")

with onglet_historique:
    chemin = os.path.join(dossier_utilisateur(), FICHIER_SAISIES)
    if os.path.exists(chemin):
        try:
            saisies = pd.read_csv(chemin)
            st.write(f"{len(saisies)} foyer(s) enregistré(s).")
            st.dataframe(saisies, hide_index=True)
            st.download_button("Télécharger l'historique (Excel)", en_xlsx(saisies, "Historique"),
                               file_name="foyers_saisis.xlsx", mime=XLSX)
        except PermissionError:
            st.warning(f"Impossible de lire {FICHIER_SAISIES} : fermez-le s'il est ouvert dans Excel, puis rechargez la page.")
    else:
        st.info("Aucun foyer enregistré pour le moment. Faites une analyse dans « Mon analyse ».")
