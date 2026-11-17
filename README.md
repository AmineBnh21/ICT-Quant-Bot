# ict-quant-bot

A rule-based forex trading bot built on ICT concepts (sessions, liquidity sweeps, fair value gaps), extended with an ML meta-labeling filter and an LLM journal reviewer.

The goal is to turn a discretionary trading plan into precise, testable rules, measure them honestly with walk-forward backtesting, and improve them with data instead of intuition.

> **Status:** work in progress. See the [Roadmap](#roadmap).

---

## Architecture

```
trading_plan.yaml  (rules extracted from the written trading plan)
        │
        ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  Data pipeline   │───▶│  Strategy (bot)  │───▶│   ML filter      │
│  OHLCV, sessions │    │  ICT rules →     │    │  meta-labeling:  │
│  news calendar   │    │  signals         │    │  take / skip     │
└──────────────────┘    └──────────────────┘    └────────┬─────────┘
                                                         ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  LLM reviewer    │◀───│  Trade journal   │◀───│  Execution       │
│  RAG over plan + │    │  SQLite, every   │    │  backtest/paper/ │
│  weekly report   │    │  trade + context │    │  live            │
└──────────────────┘    └──────────────────┘    └──────────────────┘
```

## Features

- **Plan as config:** every rule of the trading plan lives in `trading_plan.yaml` (sessions, entry conditions, risk, filters), so it can be tuned and backtested without changing code.
- **ICT building blocks:** Asian range, London / New York killzones, liquidity sweeps, fair value gaps, market structure shifts.
- **Realistic backtesting:** spread, commission and slippage included; walk-forward validation to avoid overfitting.
- **Detailed trade journal:** entry, exit, R-multiple, MAE/MFE, session, setup features, rejected signals, strategy version.
- **Performance analytics:** expectancy, profit factor, max drawdown, Sharpe, results broken down by session, pair and setup.
- **ML meta-labeling:** a classifier (XGBoost) trained on logged trades decides whether to take each signal.
- **LLM reviewer:** RAG over the trading plan PDFs; checks trades against the plan and produces a weekly report with hypotheses to test.

## Project structure

```
ict-quant-bot/
├── config/
│   └── trading_plan.yaml      # rules extracted from the trading plan
├── data/                      # raw and processed market data (gitignored)
├── docs/                      # trading plan PDFs and notes
├── src/
│   ├── data/                  # download, cleaning, sessions, news calendar
│   ├── features/              # ICT detectors: sweeps, FVG, structure
│   ├── strategy/              # rule engine reading trading_plan.yaml
│   ├── backtest/              # backtesting and walk-forward validation
│   ├── execution/             # paper / live broker connectors
│   ├── journal/               # SQLite trade logging
│   ├── ml/                    # meta-labeling model
│   └── reviewer/              # LLM + RAG journal reviewer
├── notebooks/                 # analysis and experiments
├── dashboard/                 # Streamlit performance dashboard
├── tests/
├── requirements.txt
└── README.md
```

## Tech stack

| Area | Tools |
|---|---|
| Language | Python 3.11+ |
| Data | pandas, Dukascopy / MetaTrader5 / OANDA API |
| Backtesting | backtesting.py, vectorbt |
| Storage | SQLite |
| ML | scikit-learn, XGBoost |
| LLM / RAG | LangChain or LlamaIndex, vector store (FAISS / Chroma) |
| Dashboard | Streamlit, plotly |

## Getting started

```bash
git clone https://github.com/AmineBnh21/ict-quant-bot.git
cd ict-quant-bot
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Run a backtest:

```bash
python -m src.backtest.run --config config/trading_plan.yaml --pair EURUSD --start 2020-01-01 --end 2024-12-31
```

## Roadmap

- [ ] Extract trading plan PDFs into `trading_plan.yaml`
- [ ] Data pipeline (historical OHLCV, sessions, news calendar)
- [ ] ICT feature detectors (Asian range, sweeps, FVG, structure)
- [ ] Rule-based strategy engine
- [ ] Backtesting with costs + walk-forward validation
- [ ] Trade journal (SQLite) + analytics notebook
- [ ] Streamlit dashboard
- [ ] Paper trading (demo account)
- [ ] ML meta-labeling filter, compared against the baseline bot
- [ ] LLM reviewer with RAG over the trading plan

## Results

Results will be published here once walk-forward backtests and paper trading are complete. Every reported figure will include costs and out-of-sample periods only.

## Disclaimer

This project is for educational and research purposes. It is not financial advice. Trading involves substantial risk of loss; past or backtested performance does not guarantee future results.

## Author

**Mohamed Amine Benhamaid**, M2 Artificial Intelligence student, Université Claude Bernard Lyon 1
[GitHub](https://github.com/AmineBnh21) · [LinkedIn](https://www.linkedin.com/in/mohamed-amine-benhamaid)
