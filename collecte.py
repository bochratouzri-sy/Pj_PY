"""Étape 1 du sujet : module de collecte et d'enregistrement des données d'un foyer.

Seul fichier qui ne vient pas du notebook : le sujet demande un module qui enregistre les données saisies.
"""
import os
import sys

import pandas as pd

FOURNISSEUR = {"Eau": "SONEDE", "Electricité": "STEG"}
FICHIER_SAISIES = "foyers_saisis.csv"


def dossier_utilisateur():
    """Dossier où l'application peut ÉCRIRE (à côté de l'exécutable)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def ajouter_foyer(ressource, gouvernorat, nb_personnes, superficie, index_ancien,
                  index_actuel, jours_ecoules, mois, fichier=None):
    """Enregistre les données saisies pour un foyer dans un fichier CSV."""
    fichier = fichier or os.path.join(dossier_utilisateur(), FICHIER_SAISIES)
    ligne = pd.DataFrame([{
        "date_saisie": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "ressource": ressource, "fournisseur": FOURNISSEUR.get(ressource, ""),
        "gouvernorat": gouvernorat, "nb_personnes": nb_personnes,
        "superficie_m2": superficie, "index_ancien": index_ancien,
        "index_actuel": index_actuel, "jours_ecoules": jours_ecoules, "mois": mois}])
    ligne.to_csv(fichier, mode="a", header=not os.path.exists(fichier),
                 index=False, encoding="utf-8-sig")
    return fichier
