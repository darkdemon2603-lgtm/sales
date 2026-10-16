# HANBAO Wednesday–Sunday Sales Planner

Streamlit app to allocate daily sales targets across menu items and calculate item units to sell.

## Features
- Separate sales targets for Wednesday, Thursday, Friday, Saturday, and Sunday
- Editable menu items, categories, prices, and revenue mix percentages
- Calculates item units required for each day
- Shows planned revenue after rounding and the difference from target
- Downloads item-level targets as CSV or Excel
- No API key required

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Deploy from GitHub
Upload `app.py`, `requirements.txt`, and `README.md` to a GitHub repository. Deploy `app.py` using Streamlit Community Cloud.

## Important
The example menu and revenue mix are placeholders. Replace them with your actual menu prices and ideally POS sales mix by item. The app allocates each day's target across items according to the revenue mix, then rounds quantities. This produces a practical target, but not a unique mathematically exact combination of items. Realistic item targets require a chosen sales mix or historical product sales data.
