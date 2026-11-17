# Plan de test : backtest, statistiques et simulation prop firm

Objectif : savoir **honnêtement** si la stratégie de `docs/strategy.md` gagne de l'argent, et
**quelle est la probabilité de passer le challenge Alpha Capital Pro 6 %** avec elle.

## 1. Données
- EURUSD, GBPUSD en **M1**, Dukascopy, 2015 → 2025.
- DXY **synthétique**, calculé avec la formule officielle sur 6 paires (EURUSD, USDJPY, GBPUSD, USDCAD, USDSEK, USDCHF).
- Rééchantillonnage M5 / M15 / H1 / H4 / D1, ouverture daily à 17:00 heure de New York.

## 2. Moteur de backtest
- Rejeu **bougie par bougie** : le bot ne voit jamais le futur.
- Résolution stop / cible sur le **M1**. Si les deux sont touchés dans la même minute → **perte** (choix prudent).
- Frais : spread fixe de **4 points (0,4 pip)** sur toutes les paires, **pas de commission** (compte Alpha Capital), plus slippage (`config/trading_plan.yaml`, section `costs`).
- Les données sont en BID : ASK = BID + spread. Les achats (entrée long, stop ou cible d'un short) s'exécutent sur l'ASK, les ventes sur le BID.
- Test de robustesse : on relance avec le spread × 1,5 et × 2. Si la stratégie ne gagne plus, elle est trop fragile.
- Risque dynamique : 1 % si l'équité est au-dessus du capital initial, 0,5 % sinon.

## 3. Découpage anti-sur-apprentissage
| Période | Rôle |
|---|---|
| 2015–2020 | réglage des paramètres [À VALIDER] |
| 2021–2023 | validation, walk-forward |
| 2024–2025 | test final, consulté **une seule fois** |

## 4. Journal (SQLite)
Une ligne par trade : date, paire, session, sens, C2 / C3, type de biais, DOL, entrée, stop, cible,
résultat en R, MAE / MFE, risque utilisé, confirmations présentes (SMT, PSP, type de FVG).
Les **signaux refusés** sont aussi enregistrés, avec le filtre qui les a bloqués.

## 5. Statistiques
- Win rate (seuil de rentabilité à RR 1:2 : **33,3 %**) et son intervalle de confiance à 95 %.
- Espérance en R, profit factor, rendement, drawdown max, pire série de pertes.
- Découpage par paire, session, C2 / C3, continuation / retournement, jour de la semaine, année.
- Il faut **au moins 100 à 200 trades** avant de conclure quoi que ce soit.

## 6. Simulation prop firm : Alpha Capital Pro 6 %
Règles (source officielle, vérifiée le 2026-11-17) :

| Règle | Valeur |
|---|---|
| Objectif phase 1 / phase 2 | +6 % / +6 % |
| Jours de trading minimum | 3 par phase, pas de limite de temps |
| Perte journalière max | **3 %**, mesurée depuis le plus haut entre la balance et l'équité de fin de journée précédente |
| Perte max | **6 % statique**, à partir du capital de départ |
| Compte Qualified | pas de trade 5 min autour des news, pas de position le week-end |

**Ce que la simulation calcule :**
1. On découpe l'historique hors échantillon en de nombreux « challenges » qui démarrent à des dates différentes.
2. Pour chacun, on applique les règles ci-dessus **en équité, minute par minute** (la perte journalière compte aussi les pertes latentes).
3. Plus un **Monte Carlo** : 10 000 tirages de l'ordre des trades.

**Résultats attendus :**
- **Probabilité de passer la phase 1**, puis la phase 2, puis les deux.
- **Probabilité d'échec**, et pourquoi (perte max 6 % ou perte journalière 3 %).
- **Temps médian** pour passer (en jours, en nombre de trades).
- Comparaison de variantes de risque : 0,5 % fixe, 1 % fixe, et ta règle 1 % / 0,5 %.

**Calcul rapide avec tes règles (RR 1:2) :**
- En partant de 0 et à 0,5 % de risque, il faut **12 pertes d'affilée** pour toucher les -6 %.
- Avec 1 trade par jour et au maximum 1 % de risque, la limite journalière de 3 % ne peut pas être touchée par un seul trade.
- Pour +6 % : environ 3 gains à 2 % (risque 1 %, une fois en positif) ; un premier gain à 0,5 % de risque rapporte +1 %.

## 7. Après le backtest
Paper trading sur un compte démo pendant 1 à 3 mois, comparaison avec le backtest, puis meta-labeling.
