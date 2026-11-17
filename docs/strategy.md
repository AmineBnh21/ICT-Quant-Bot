# Stratégie : Fractal Model C2/C3/C4 sur EURUSD et GBPUSD

Ce document traduit les PDFs de `docs/` (Arjo / MMT, TTrades, MZ Trader) en règles **précises et codables**.
Chaque règle a une source. Les choix qui n'existent pas dans les PDFs sont marqués **[À VALIDER]** :
ce sont des paramètres que le backtest devra trancher.

- **Marchés :** EURUSD, GBPUSD (+ DXY et EURGBP comme marchés de confirmation)
- **Heure de référence :** New York (America/New_York). En forex la bougie daily ouvre à **17:00 NY**.
- **Modèle :** Fractal Model de TTrades (C1 → C2 → C3 → C4), qui est le même modèle que le « C2 / C3 / C4 » de MZ Trader et le CRT.

---

## 0. Vue d'ensemble

```
1. BIAIS        HTF (Weekly / Daily)  → quelle direction ? quelle bougie (C2, C3, C4) ?
2. DOL          HTF                   → vers quel PD Array / quelle liquidité va-t-on ? (la cible)
3. NARRATIVE    HTF                   → depuis quel PD Array part-on ? (FLOD / OD / LLOD)
4. CONFIRMATION timeframe aligné       → CISD (+ SMT / PSP en bonus)
5. ENTRÉE       LTF, dans la killzone  → limit sur le CISD / FVG, stop au swing, cible 2R ou DOL
```

> « Price is always moving towards a PD Array. It's our job to find out which one is next. » (Arjo, PD Arrays)

---

## 1. Briques de base (détecteurs)

### 1.1 Fair Value Gap (FVG), *source : Arjo 6, TTrades FVG*
Sur 3 bougies consécutives `c1, c2, c3` :
- **FVG haussière (BISI)** : `c1.high < c3.low` → zone `[c1.high, c3.low]`
- **FVG baissière (SIBI)** : `c1.low > c3.high` → zone `[c3.high, c1.low]`
- Taille minimale : **[À VALIDER]**, proposition `≥ 0.1 × ATR(14)` du timeframe.

**Qualité d'une FVG** (Arjo 6), selon la 3e bougie :
| Type | 3e bougie | Qualité pour trader *depuis* |
|---|---|---|
| PFVG (Perfect) | consolidation (petit corps) | **meilleure** |
| BAG (Breakaway) | expansion (grand corps) | moyenne, seulement si le PD Array opposé n'est pas encore atteint |
| RFVG | rejet (grande mèche opposée) | **pire**, demande plus de confirmation |

**Inversion (IFVG)** : une FVG est *inversée* quand une bougie **clôture** de l'autre côté de la zone, qui change alors de rôle.

### 1.2 Swing points, *source : TTrades One Model / Relevant Highs-Lows, Arjo 2*
- **Swing low** : bougie `i` telle que `low[i] < low[i-1]` et `low[i] < low[i+1]` (fractale de 3 bougies). Même chose à l'envers pour le swing high.
- **Swing pertinent (relevant)** : un swing dont on s'est éloigné avec une *séparation valide*, c'est-à-dire qu'une bougie a clôturé au-delà du corps de la bougie de swing **[À VALIDER : définition exacte de la séparation]**.
- **Lookback** : on ne regarde que les swings des **3 dernières bougies HTF** (TTrades, Relevant Highs/Lows).
- Hiérarchie (Arjo 2-3) :
  - **STH / STL** (Short Term) : swing suivi d'une FVG, base de l'*order flow*.
  - **ITH / ITL** (Intermediate Term) : swing de structure. Sur le Daily, STH = ITH.

### 1.3 Fair Value Area (FVA), *source : Arjo 2, 7*
Zone créée **quand un swing précédent est pris**. Range du swing (ITH → ITL en structure, STH → STL en order flow).
Qualité (de la meilleure à la pire) : FVA + FVG chevauchante + FVA imbriquée > FVA + FVG > FVA de simple sweep.

### 1.4 PD Arrays : Premium / Discount, *source : Arjo 1, TTrades Discount & Premium, Dealing Ranges*
Les 3 PD Arrays : **FVG**, **FVA**, **swing points** (liquidité, y compris PCH / PCL = haut et bas de la bougie précédente).
- **Premium Array** (au-dessus du prix / dans la moitié haute du range) : on attend une réaction **baissière**.
- **Discount Array** (en dessous / moitié basse) : on attend une réaction **haussière**.
- **Equilibrium (EQ)** = 0.5 du dealing range ou de la bougie.

### 1.5 Respect / Disrespect, *source : Arjo PD Arrays, 2CR E-Book*
C'est **le concept central**. Un PD Array touché par une bougie est :
- **Respecté** : la bougie entre dans la zone avec une mèche mais **clôture du bon côté** (rejet).
- **Disrespecté** : la bougie **clôture à travers** la zone. Disrespecter un swing = *run on liquidity*.

**2 Candle Rejection (2CR)** : un PD Array a **2 occasions** de rejeter :
1. la **1re bougie** qui le touche rejette, ou
2. la 1re ne rejette pas, mais la **2e bougie rejette le PCH / PCL** (le haut / bas de la 1re).

| Situation | Lecture |
|---|---|
| Premium disrespecté + Discount respecté | **Tendance haussière** |
| Premium respecté + Discount disrespecté | **Tendance baissière** |
| Premium respecté + Discount respecté | **Consolidation (50/50) : PAS DE TRADE** |
| 2CR haussier ensuite disrespecté | l'intention redevient baissière |

### 1.6 Order Flow Leg, *source : Arjo 3, 5, 10*
Une jambe d'order flow contient les 3 PD Arrays. Pas de FVG = pas de jambe.
Zones de défense lors d'un retracement (= **zones de contexte**, là où on peut entrer) :
- **FLOD** (First Line of Defense) : la 1re FVG rencontrée.
- **OD / OLOD** (Overlapping Defense) : la 1re zone où FVA et FVG se chevauchent.
- **LLOD** (Last Line of Defense) : le swing d'origine. Au-delà, l'idée est invalidée.

Choix FLOD ou OD : si on vient de prendre un ITH / ITL → on attend l'**OD (FVA)**, sinon la **FLOD**.

### 1.7 CISD : Change in State of Delivery, *source : TTrades CISD, One Model*
Après un mouvement vers un **niveau important** :
- **CISD haussier** : on prend la série de bougies baissières consécutives qui a fait le dernier mouvement ; le CISD est validé quand une bougie **clôture au-dessus de l'open de la 1re bougie de cette série**.
- **CISD baissier** : l'inverse.
- Le niveau CISD (cet open) sert de **prix d'entrée en limit** (TTrades, Alignment with Bias).

**MSS** (Market Structure Shift) = clôture au-delà du dernier swing opposé. Plus lent que le CISD, utilisé comme confirmation alternative (MZ Trader).

### 1.8 CRT : Candle Range Theory, *source : CRT by MZ, Order Flow + CRT*
Une bougie HTF définit un range (CRT High / CRT Low). La bougie suivante **balaie** un extrême puis **clôture à l'intérieur** du range → cible = l'extrême opposé.
Variantes : 2 bougies, multi-bougies, inside bar, double purge, continuation.
→ Le CRT est exactement le **C2** du Fractal Model.

---

## 2. Biais : le Fractal Model (C1 → C4)

### 2.1 Numérotation des bougies, *source : TTrades One Model 2026, Keep it Simple, MZ C2/C3*
Sur le timeframe de biais (**Daily** par défaut) :

| Bougie | Rôle (exemple haussier) | Règle de détection |
|---|---|---|
| **C1** | bougie de référence | – |
| **C2** | **balaie le bas de C1** (prise de liquidité) et clôture **au-dessus du bas de C1** | `low[C2] < low[C1]` et `close[C2] > low[C1]` → swing low formé |
| **C3** | **expansion** : clôture au-dessus du haut de C2 | `close[C3] > high[C2]` |
| **C4** | **continuation** après C3 | prend le haut de C3 |

### 2.2 Les 4 biais daily, *source : One Model 2026, Easy Daily Bias, Daily Bias*
- **Continuation haussière** : la bougie d'hier a **clôturé au-dessus du PDH** → DOL = haut d'hier ; entrée possible sur retracement vers l'EQ (0.5) de la bougie d'hier.
- **Retournement haussier** : la bougie d'hier a **balayé le PDL et clôturé à l'intérieur** (C2 / CRT) → DOL = PDH.
- Mêmes règles à l'envers pour le baissier.
- **Pas de biais** : inside bar, ou bougie qui clôture au milieu sans rien prendre → **pas de trade** (ou attendre une prise de liquidité claire).

### 2.3 Quelle bougie trader ? *source : MZ Trader, « C2 and C3 : One model for life »*
- **C3 = trade de plus haute probabilité** (C2 déjà confirmée).
- **C2 = haut risque** : il faut **plus de confirmations** (CISD 4H + CISD 1H + fractale 4H).
- **C4 = continuation** : à éviter si la cible HTF est déjà prise (TTrades, Why Your Continuations Fail).

### 2.4 Top-down et validation du biais, *source : Arjo 4 et 12, TTrades Top Down, Alignment with Bias*
1. **Monthly / Weekly** : Candle Science (respect ou disrespect des PD Arrays HTF).
2. **Daily** : Order Flow + numéro de bougie (C2, C3, C4).
3. **4H / 1H** : structure intraday. Le biais daily est **confirmé** par un **CISD 1H** dans le sens du biais (Keep it Simple : « Bearish Daily C2 is confirmed by a bearish hourly CISD »).

**Invalidation du biais** (TTrades, Trading Invalidation of Bias) : si le prix casse l'EQ (0.5) contre le biais ou forme un retournement contraire sur PDH / PDL → biais invalidé, on arrête de chercher des entrées dans ce sens.

---

## 3. Draw on Liquidity (DOL) : la cible

*Sources : Easiest DOL, Important Liquidity Levels, Liquidity Buyside & Sellside, IRL to ERL*

Liste des liquidités, par ordre de priorité **[À VALIDER : l'ordre]** :
1. **PDH / PDL** (haut / bas du jour précédent) : la DOL la plus simple.
2. **3-day lookback** : plus haut / plus bas des 3 derniers jours.
3. **PWH / PWL** (semaine précédente), puis mois précédent.
4. **Swings HTF pertinents** (ERL = External Range Liquidity).
5. **FVG HTF non comblées** (IRL = Internal Range Liquidity).
6. **Highs / lows de session** (Asie, Londres).

**Relation IRL / ERL** : après une prise d'ERL (un swing) → le prix va vers l'IRL (une FVG), et inversement.
**Règle** : la DOL choisie est le **PD Array opposé le plus proche dans le sens du biais**.

---

## 4. Confirmation : alignement des timeframes

*Source : TTrades Timeframe Alignment, Entry Timing, Arjo 11*

| Biais / structure (HTF) | Confirmation CISD (LTF) |
|---|---|
| Weekly | 4H |
| **Daily** | **1H** ← modèle principal |
| 4H | 15m |
| 1H | 5m |

**Modèle « Keep it Simple / Favorite Fractal Model »** : Daily (biais) → 4H / 1H (structure) → **15m / 5m** (CISD d'entrée).

Confirmations bonus (enregistrées comme *features* pour le ML, pas obligatoires dans la v1) :
- **SMT EURUSD / GBPUSD** : l'une fait un nouveau bas, l'autre non (divergence au swing).
- **SMT avec DXY** (corrélation inverse).
- **PSP** : à la bougie de swing, une paire clôture haussière et l'autre baissière.
- **Force relative EURGBP** : EURGBP haussier → privilégier les longs EURUSD et les shorts GBPUSD.

---

## 5. Entrée, stop, cible, gestion

*Sources : Arjo 11, TTrades Stop Losses, Dealing Ranges, Entry Timing, MZ Trader*

- **Fenêtre de temps (forex, heure NY)** : Londres **02:00–05:00**, New York **07:00–10:00** (Arjo : « Forex 2am–10am »). En dehors : pas d'entrée.
- **Entrée** : ordre **limit** au niveau du CISD (open de la série), ou dans la FVG créée par le CISD.
- **Stop** : au-delà du swing qui a formé le CISD (*opposing swing*), ou au-delà du corps (*opposing body*, stop plus serré) **[À VALIDER]**.
- **Cible** : **toujours 2R (RR 1:2 fixe)**. On garde le trade seulement si la DOL est à ≥ 2R ; sinon, pas de trade.
- **Risque par trade (dynamique)** :
  - **1 %** du compte si l'équité est **au-dessus du capital initial** (compte en positif) ;
  - **0.5 %** si l'équité est **au niveau du capital initial ou en dessous**.
  - Le palier est recalculé avant chaque trade.
- **Break-even** : quand l'order flow ne donne plus de raison de revenir sur l'entrée **[À VALIDER : règle mécanique, par exemple à +1R]**.
- **Fréquence** : **1 trade par jour** (Arjo 11).
- **Contexte « dealing range »** : long en discount, short en premium (le contre-sens est permis mais noté).

---

## 6. Filtres (quand NE PAS trader)

| Filtre | Source |
|---|---|
| Consolidation : premium **et** discount respectés (50/50) | 2CR E-Book, Arjo PD Arrays |
| La cible HTF est déjà prise → pas de continuation | Why Your Continuations Fail |
| La cible court terme est déjà prise avant l'entrée | Why Your Continuations Fail |
| Entrée contre le biais HTF | Alignment with Bias |
| News majeures (NFP, CPI, FOMC) ce jour-là : pas de trade, ou risque réduit | Arjo 9 (Time) |
| Pas de FVG dans la jambe → pas d'order flow → pas de trade | Arjo 3 |
| Hors killzone | Arjo 11 |

---

## 7. Version 1 du bot (le modèle minimal à backtester d'abord)

```
SI   biais daily = C2 ou C3 (via 2.1 / 2.2)
ET   la DOL daily est dans le sens du biais, à ≥ 2R
ET   pas de filtre de la section 6
ET   on est dans la killzone de Londres ou de New York
ET   le prix est dans une zone de contexte (FLOD / OD) en discount pour un long (premium pour un short)
ET   un CISD 15m (ou 5m) se forme dans le sens du biais
ALORS limit au niveau du CISD, stop au swing, cible 2R fixe
     risque = 1 % si le compte est en positif, sinon 0.5 %
```

Ensuite on ajoute **une règle à la fois** et on la garde seulement si elle améliore les résultats **hors échantillon** :
CISD 1H obligatoire → SMT / PSP → qualité de FVG (PFVG, BAG, RFVG) → biais Weekly → filtre news → C4.

**Résultats v1 (2015-2026, M15) :** seule la règle « long sous l'EQ de la veille, short au-dessus » a amélioré
les deux périodes. FVG H1, CISD H1 seul et stops plus larges ont été écartés (voir l'historique git).

---

## 7 bis. Version 2 : top-down Monthly → Weekly → Daily, puis H4 → H1 → M15

**Règle de l'utilisateur :** on connaît d'abord le biais HTF, ensuite seulement on descend.
**Le M15 est le plus petit timeframe** : pas de M5, pas de M1 (le M1 sert uniquement au moteur pour savoir
si le stop ou la cible est touché en premier).

### Biais d'un timeframe HTF (MN1, W1, D1), calculé sur la dernière bougie TERMINÉE
Trois éléments, d'après l'utilisateur :
1. **PD Arrays respectés / disrespectés** (Arjo, section 1.5). PD Arrays suivis sur ce timeframe :
   FVG et swing points. À chaque bougie terminée :
   - elle touche un **discount array** (FVG haussière, swing low) et clôture au-dessus → **respect → +1** ;
     elle clôture à travers → **disrespect → −1** ;
   - elle touche un **premium array** (FVG baissière, swing high) et clôture en dessous → **respect → −1** ;
     elle clôture à travers → **disrespect → +1**.
   La dernière réaction connue donne le sens « PD Arrays » (il reste valable jusqu'à la réaction suivante).
2. **Bougie C2 / continuation** (section 2.2) : sens de la dernière bougie.
3. **Premium / discount** du range de la dernière bougie terminée (EQ 0,5) : sert de **filtre d'emplacement**
   (long seulement en discount, short seulement en premium).

Sens du timeframe = 1 et 2 combinés : s'ils sont d'accord, ou si l'un est neutre → ce sens ; s'ils s'opposent → neutre.

### Alignement top-down
- **Daily** non neutre (obligatoire) ;
- **Weekly** dans le même sens que le Daily (ou neutre) ;
- **Monthly** pas dans le sens opposé.

## 7 ter. Les deux modèles CRT haute probabilité (règles de l'utilisateur)

L'utilisateur trade **uniquement ces deux modèles**, construits de la même façon (fractal) :

| Modèle | CRT C1-C2-C3 (X) | Confirmation (Y) | Entrée (Z) |
|---|---|---|---|
| **4H** | H4 | H1 | M15 |
| **Daily** | D1 | H4 | H1 |

Pour un long (inverse pour un short) :
1. **CRT sur X**, deux setups tradés :
   - **C3** : la dernière bougie X terminée est un C2 haussier (balayage du bas de C1, clôture dans le range
     de C1) → on trade la bougie X en cours ;
   - **C2** : la bougie X en cours a déjà balayé le bas de la précédente (C1) sans prendre son haut.
   Cible = **haut de C1 (CRT High)**.
2. **Confirmation sur Y** après le balayage : **CISD** OU **#01 First Opposing Candle** (MZ Trader : première
   bougie Y haussière qui clôture, à partir de la bougie du balayage).
3. **Entrée sur Z** : CISD dans le sens du trade, formé après la confirmation, dans une killzone. Limit au niveau
   du CISD, stop au-delà de l'extrême, **cible 2R fixe** (le CRT High doit être au-delà, et pas encore pris).
   Entrée dans la moitié discount du range de C1 (sous son 0,5).
4. Option **top-down** : biais Weekly et Monthly (section 7 bis) pas dans le sens opposé.
5. **Sortie dans la journée, pour les deux modèles** (confirmé par l'utilisateur) : si ni la cible ni le stop
   ne sont touchés, le trade est fermé avant la fin du jour de trading (16:55 New York, avant le rollover).
   Aucune position n'est gardée au lendemain.

Code : `src/backtest/strategy_crt.py` ; comparaison : `python -m src.backtest.run --crt`.

---

## 8. Questions à tester avec les données (avant le bot)

1. Après une clôture daily au-dessus du PDH, quel % des jours prend le PDH suivant ? (continuation)
2. Après un C2 daily (balayage du PDL puis clôture à l'intérieur), quel % des jours atteint le PDH ?
3. C3 a-t-il vraiment un meilleur taux de réussite que C2 ? (affirmation MZ Trader)
4. Une PFVG tient-elle plus souvent qu'une BAG ou une RFVG ? (affirmation Arjo)
5. Le SMT EURUSD / GBPUSD améliore-t-il le taux de réussite du CISD ?
6. Londres ou New York : quelle killzone donne le meilleur résultat par paire ?

---

## 9. Paramètres ouverts [À VALIDER]
- Taille minimale d'une FVG (en ATR ou en pips).
- Définition exacte de la « séparation valide » d'un swing.
- Stop : *opposing swing* ou *opposing body*.
- Règle mécanique de break-even.
- Ordre de priorité des DOL.
- Faut-il exiger la clôture du C2 avant d'entrer (entrée en C3), ou entrer pendant le C2 (plus tôt, plus risqué) ?
