# HANBAO Sales Target & Forecasting Engine

A Streamlit starter app that turns revenue targets into customer-demand forecasts, scenario planning, indicative menu quantities, gross-profit estimates and a trackable action plan.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows
pip install -r requirements.txt
streamlit run app.py
```

## Deploy from GitHub to Streamlit Community Cloud

1. Create a GitHub repository.
2. Add `app.py`, `requirements.txt`, and this README.
3. In Streamlit Community Cloud, deploy the repository and select `app.py` as the entry point.
4. Replace the sample menu with your real menu and upload historical sales exports.

## CSV formats

### Menu CSV (required columns)

- `item`
- `category`
- `price_gbp`

Optional:
- `sales_mix_pct` — expected share of revenue; should total 100%.
- `food_cost_per_unit_gbp` — ingredient/packaging cost per unit, on a consistent VAT basis.

### Historical sales CSV

Minimum:
- `date`
- `net_sales_gbp`

Recommended:
- `location`
- `item`
- `category`
- `quantity`
- `price_gbp`
- `food_cost_per_unit_gbp`
- `transaction_id`
- `covers`

If `net_sales_gbp` is absent, the app can calculate it from `quantity * price_gbp`.

### Transaction / covers CSV (optional starter input)

Useful columns:
- `date`
- `location`
- `transaction_id`
- `covers`
- `transaction_value_gbp`

## Important limitations

This is a starter implementation. It does not yet connect directly to a POS, bookings platform, weather service or marketing platform. The forecast is driven by user-entered covers and average spend; historical revenue is shown as a comparison rather than automatically being used as a blended forecast. Item-level quantities are indicative and independently rounded, not a true basket-level model. Validate all assumptions before using it for staffing, stock or commercial decisions.

## Suggested next development steps

1. Match the import schema to the actual POS export.
2. Add persistent storage (for example, a database) so action plans and forecasts survive app restarts.
3. Add transaction-level basket analysis to estimate attachment rates and items per order.
4. Add historical forecast accuracy tracking.
5. Add food-cost completeness checks and a fuller contribution-margin model.
