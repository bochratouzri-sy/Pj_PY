"""Étape 3 : évaluation et comparaison des modèles
 (n'est pas nécessaire à l'application).
"""
from donnees import D, P, UNITE
from fonctions import SEUIL, M_FACTURE, M_CONSO



# =====================  évaluation (GroupKFold) =====================
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import (GroupKFold,GroupShuffleSplit,cross_validate)
from sklearn.ensemble import (RandomForestRegressor,HistGradientBoostingRegressor,IsolationForest)
from sklearn.dummy import DummyRegressor
from sklearn.metrics import (precision_score,recall_score,f1_score)

gkf = GroupKFold(n_splits=5)

def modeles():
    return {"Référence (médiane)": DummyRegressor(strategy="median"),"Régression linéaire": LinearRegression(),
            "Random Forest": RandomForestRegressor(n_estimators=200,min_samples_leaf=5,random_state=0),
            "Gradient Boosting": HistGradientBoostingRegressor(max_iter=150,max_depth=3,learning_rate=0.05,random_state=0)}

def evaluer(X,y,groupes):
    lignes = []
    if pd.Series(groupes).nunique() < 5:
        raise ValueError("Il faut au minimum 5 foyers différents pour effectuer une validation GroupKFold.")
    for nom,m in modeles().items():
        s = cross_validate(m,X,y,cv=gkf,groups=groupes,scoring=["neg_mean_absolute_error","neg_root_mean_squared_error","r2"])
        lignes.append({"modèle":nom,"MAE":-s["test_neg_mean_absolute_error"].mean(),
                       "RMSE":-s["test_neg_root_mean_squared_error"].mean(),"R²":s["test_r2"].mean()})
    return pd.DataFrame(lignes).round(2).set_index("modèle")

for r,d in D.items():
    print(f"\n{'#'*50}")
    print(f"RESSOURCE : {r}")
    print(f"{'#'*50}")
    groupes = d["foyer_ref"].to_numpy()
    print(f"\n--- F1 : facture ({r}, DT) ---")
    X_facture = d[["conso_periode","nb_mois"]]
    y_facture = d["montant_facture_dt"]
    resultat_facture = evaluer(X_facture,y_facture,groupes)
    print(resultat_facture)

    print(f"\n--- F2 : consommation attendue ({UNITE[r]}/mois) ---")
    X_conso = P[r]
    y_conso = d["conso_mensuelle"]
    resultat_conso = evaluer(X_conso,y_conso,groupes)
    print(resultat_conso)

    print("\n--- F3 : détection des anomalies simulées ---")
    X = np.column_stack([P[r],d["conso_mensuelle"].to_numpy(),d["mois"].to_numpy()])
    separation = GroupShuffleSplit(n_splits=1,test_size=0.30,random_state=0)
    indices_train,indices_test = next(separation.split(X,groups=groupes))
    Xtr = X[indices_train]
    Xte = X[indices_test]
    foyers_train = set(groupes[indices_train])
    foyers_test = set(groupes[indices_test])
    assert foyers_train.isdisjoint(foyers_test),("Erreur : certains foyers sont présents dans les deux ensembles.")
    print("Nombre de foyers entraînement :",len(foyers_train))
    print("Nombre de foyers test :",len(foyers_test))

    ref = LinearRegression().fit(Xtr[:,:-2],Xtr[:,-2])
    multiplicateur = np.r_[np.ones(X.shape[1]-2),3,1]
    X_anormal = Xte*multiplicateur
    Xt = np.vstack([Xte,X_anormal])
    yt = np.r_[np.zeros(len(Xte)),np.ones(len(Xte))]

    isolation = IsolationForest(contamination=0.03,random_state=0)
    isolation.fit(Xtr)
    prediction_isolation = (isolation.predict(Xt)==-1)
    prediction_seuil = (Xt[:,-2]>SEUIL*ref.predict(Xt[:,:-2]))
    predictions = {"Isolation Forest":prediction_isolation,f"Règle > {SEUIL}x attendu":prediction_seuil}
    resultats_anomalies = {}
    for nom,prediction in predictions.items():
        resultats_anomalies[nom] = {"Précision":precision_score(yt,prediction,zero_division=0),
                                    "Rappel":recall_score(yt,prediction,zero_division=0),
                                    "F1":f1_score(yt,prediction,zero_division=0)}
    tableau_anomalies = pd.DataFrame(resultats_anomalies).T.round(2)
    print(tableau_anomalies)

print("\nÉVALUATION TERMINÉE.")


# =====================  test sur un exemple =====================
print("-------TEST F1 : ESTIMATION DES FACTURES ---------")

for r,d in D.items():
    X_test_facture = d[["conso_periode","nb_mois"]].iloc[[0]]
    facture_reelle = d["montant_facture_dt"].iloc[0]
    facture_predite = M_FACTURE[r].predict(X_test_facture)[0]
    print(f"\nRessource : {r}")
    print(f"Facture reelle : {facture_reelle:.2f} DT")
    print(f"Facture predite : {facture_predite:.2f} DT")
    print(f"Erreur : {abs(facture_reelle-facture_predite):.2f} DT")

print("\n-------- TEST F2 : CONSOMMATION ATTENDUE -------")

for r,d in D.items():
    X_test_conso = P[r][:1]
    conso_reelle = d["conso_mensuelle"].iloc[0]
    conso_predite = M_CONSO[r].predict(X_test_conso)[0]
    print(f"\nRessource : {r}")
    print(f"Consommation reelle : {conso_reelle:.2f}")
    print(f"Consommation predite : {conso_predite:.2f}")
    print(f"Erreur : {abs(conso_reelle-conso_predite):.2f}")

print("\n-------- TESTS TERMINES ---------")