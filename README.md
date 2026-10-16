# HANBAO Sales-to-Customer Planner

A Streamlit app that reverse-plans a revenue target into required customer visits, estimated unique customers, and daily sales targets.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

1. Push `app.py`, `requirements.txt`, and `README.md` to a GitHub repository.
2. Create an app in Streamlit Community Cloud and select `app.py`.
3. No API key is required.

## Model assumptions

- Required visits = revenue target (including optional buffer) / average spend per visit.
- Visits are split into returning and new/one-time visits using the returning-visit share.
- Estimated unique returning customers = returning visits / average visits per returning customer.
- Estimated unique customers = estimated unique returning customers + new/one-time visits.

These are planning estimates, not a demand prediction. Replace assumptions with actual business data where possible.

## Historical sales CSV

The app recognises common revenue columns such as `revenue`, `sales`, `total`, `order_total`, `amount`, and `net_sales`.

For unique customer and repeat-visit analysis, include a `customer_id` and preferably an `order_id`. Without customer IDs, true unique customers cannot be reliably measured.
