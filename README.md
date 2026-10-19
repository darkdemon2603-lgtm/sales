# HANBAO Sales Forecasting Engine

A Streamlit app for manually entering daily revenue forecasts, automatically calculating the covers needed, reporting gross and net revenue, comparing against historical sales, and estimating menu demand and gross profit.

## What the app does

- Manually enter forecast revenue for each forecast date.
- Automatically calculate covers as forecast revenue divided by average spend per cover, rounded up to a whole cover.
- Convert gross revenue (including VAT) to net revenue (excluding VAT), or vice versa, using the configurable VAT rate.
- Show forecast gross revenue, net revenue, VAT element, covers, and average spend.
- Upload historical sales CSVs to compare historical performance and suggest average spend per cover where cover data is available.
- Upload/edit menu data to estimate item quantities and gross profit using menu revenue mix and food costs.
- Export the forecast to Excel or CSV.

**The Scenario Planner has been removed.** Forecast revenue is entered manually.

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
2. Add `app.py`, `requirements.txt`, `README.md`, `hanbao_menu_template.csv`, and `hanbao_historical_sales_template.csv`.
3. In Streamlit Community Cloud, deploy the repository and select `app.py` as the entry point.
4. Upload your actual menu and historical sales CSVs in the app.

## Menu CSV

Required columns:
- `item`
- `category`
- `price_gbp`

Optional columns:
- `sales_mix_pct` — expected share of net revenue; should total 100% for item-level estimates.
- `food_cost_per_unit_gbp` — food/packaging cost per unit. Use a consistent cost basis.

The included menu template has illustrative sample items and prices. Replace them with HANBAO's actual menu and costs.

## Historical sales CSV

Recommended columns:
- `date`
- `location`
- `gross_sales_gbp` — revenue including VAT
- `net_sales_gbp` — revenue excluding VAT
- `covers` — customer covers for the trading date (daily totals are recommended)
- `transactions`
- `avg_spend_gross_gbp`
- `avg_spend_net_gbp`
- `item`
- `category`
- `quantity`
- `price_gbp`
- `food_cost_per_unit_gbp`
- `transaction_id`

At minimum, provide `date` and one usable revenue field (`gross_sales_gbp` or `net_sales_gbp`), or item quantity and price. If only one of gross or net revenue is provided, the app derives the other using the configured VAT rate.

For accurate average spend per cover suggestions, include daily covers alongside daily gross/net revenue. If the CSV contains item-level rows, ensure daily cover values are not repeated in a way that makes them add up multiple times; the app uses the maximum covers value per date when summarising daily history.

## Gross, net and VAT

- **Gross revenue** includes VAT.
- **Net revenue** excludes VAT.
- The VAT rate is configurable in the sidebar and defaults to 20%.
- The conversion assumes the same VAT rate applies to all forecast revenue. If your sales include different VAT treatments, split the sales by VAT category or validate the figures separately.
- The average spend per cover input must use the same basis (gross or net) selected for manual forecast revenue.

## Important limitations

- This is a planning tool and does not connect directly to Tevalis or SevenRooms. Import CSV exports.
- Historical comparisons are context only and do not change your manually entered forecast.
- Menu quantities are independently rounded estimates based on revenue mix, not a transaction-level basket model.
- Estimated gross profit is net menu sales minus entered food costs. It excludes labour, rent, utilities, payment fees and other operating costs.
- Validate the mapping and VAT basis of actual POS exports before using outputs for operational decisions.
