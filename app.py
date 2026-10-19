import io
from datetime import date, timedelta

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="HANBAO Sales Forecasting Engine",
    page_icon="🍔",
    layout="wide",
)

# ----------------------------
# Helpers
# ----------------------------
def money(value):
    try:
        if pd.isna(value):
            return "—"
        return f"£{float(value):,.2f}"
    except (TypeError, ValueError):
        return "—"


def clean_columns(df):
    df = df.copy()
    df.columns = [
        str(c).strip().lower().replace(" ", "_").replace("-", "_")
        for c in df.columns
    ]
    aliases = {
        "menu_item": "item",
        "product": "item",
        "product_name": "item",
        "selling_price": "price_gbp",
        "price": "price_gbp",
        "unit_price": "price_gbp",
        "units": "quantity",
        "qty": "quantity",
        "units_sold": "quantity",
        "sales": "net_sales_gbp",
        "net_sales": "net_sales_gbp",
        "gross_sales": "gross_sales_gbp",
        "gross_revenue": "gross_sales_gbp",
        "net_revenue": "net_sales_gbp",
        "food_cost": "food_cost_per_unit_gbp",
        "unit_food_cost": "food_cost_per_unit_gbp",
        "transaction": "transaction_id",
        "order_id": "transaction_id",
        "venue": "location",
        "site": "location",
        "customer_covers": "covers",
        "guests": "covers",
        "transactions_count": "transactions",
    }
    return df.rename(columns={c: aliases.get(c, c) for c in df.columns})


def load_csv(uploaded_file):
    if uploaded_file is None:
        return None
    try:
        return clean_columns(pd.read_csv(uploaded_file))
    except Exception as exc:
        st.error(f"Could not read {uploaded_file.name}: {exc}")
        return None


def safe_numeric(df, columns):
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def normalise_menu(df):
    required = {"item", "category", "price_gbp"}
    if df is None or not required.issubset(df.columns):
        return None
    out = df.copy()
    out["item"] = out["item"].astype(str).str.strip()
    out["category"] = out["category"].astype(str).str.strip()
    out = safe_numeric(out, ["price_gbp", "sales_mix_pct", "food_cost_per_unit_gbp"])
    if "sales_mix_pct" not in out:
        out["sales_mix_pct"] = np.nan
    if "food_cost_per_unit_gbp" not in out:
        out["food_cost_per_unit_gbp"] = np.nan
    out = out.dropna(subset=["item", "category", "price_gbp"])
    return out[out["price_gbp"] > 0].copy()


def normalise_history(df, vat_rate):
    if df is None or "date" not in df.columns:
        return None

    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    out = safe_numeric(
        out,
        [
            "quantity", "price_gbp", "gross_sales_gbp", "net_sales_gbp",
            "food_cost_per_unit_gbp", "covers", "transactions",
            "avg_spend_gross_gbp", "avg_spend_net_gbp",
        ],
    )

    if "location" not in out:
        out["location"] = "All locations"
    if "item" not in out:
        out["item"] = "All items"
    if "category" not in out:
        out["category"] = "Uncategorised"
    out["location"] = out["location"].fillna("All locations").astype(str)

    factor = 1 + float(vat_rate) / 100
    if "net_sales_gbp" not in out:
        out["net_sales_gbp"] = np.nan
    if "gross_sales_gbp" not in out:
        out["gross_sales_gbp"] = np.nan

    # Derive item sales if no explicit sales amount was provided.
    item_calc = (
        out["quantity"] * out["price_gbp"]
        if {"quantity", "price_gbp"}.issubset(out.columns)
        else pd.Series(np.nan, index=out.index)
    )
    out["net_sales_gbp"] = out["net_sales_gbp"].where(
        out["net_sales_gbp"].notna(), item_calc
    )
    out["gross_sales_gbp"] = out["gross_sales_gbp"].where(
        out["gross_sales_gbp"].notna(), out["net_sales_gbp"] * factor
    )
    out["net_sales_gbp"] = out["net_sales_gbp"].where(
        out["net_sales_gbp"].notna(), out["gross_sales_gbp"] / factor
    )

    out = out.dropna(subset=["date"])
    out = out[
        (out["net_sales_gbp"].fillna(-1) >= 0)
        | (out["gross_sales_gbp"].fillna(-1) >= 0)
    ]
    return out


def build_sample_menu():
    return pd.DataFrame(
        [
            ["Cheeseburger", "Burgers", 10.50, 25, 3.50],
            ["Double Burger", "Burgers", 13.50, 15, 4.60],
            ["Chicken Burger", "Burgers", 12.50, 12, 4.20],
            ["Vegan Burger", "Burgers", 12.00, 5, 3.80],
            ["Fries", "Sides", 4.50, 15, 1.10],
            ["Loaded Fries", "Sides", 7.00, 8, 2.10],
            ["Chicken Tenders", "Sides", 7.50, 6, 2.50],
            ["Soft Drink", "Drinks", 3.00, 10, 0.60],
            ["Milkshake", "Drinks", 5.50, 2, 1.30],
            ["Dessert", "Desserts", 6.00, 2, 1.70],
        ],
        columns=[
            "item", "category", "price_gbp", "sales_mix_pct",
            "food_cost_per_unit_gbp",
        ],
    )


def daily_history_summary(history, location, target_date):
    if history is None or history.empty:
        return None
    hist = history.copy()
    if location != "All locations":
        hist = hist[hist["location"].str.casefold() == location.casefold()]
    if hist.empty:
        return None

    hist["date_dt"] = pd.to_datetime(hist["date"], errors="coerce")
    hist = hist.dropna(subset=["date_dt"])
    daily = hist.groupby(hist["date_dt"].dt.date, as_index=False).agg(
        net_sales_gbp=("net_sales_gbp", "sum"),
        gross_sales_gbp=("gross_sales_gbp", "sum"),
        covers=("covers", "max"),
    )
    daily["date_dt"] = pd.to_datetime(daily["date"])
    daily["weekday"] = daily["date_dt"].dt.day_name()
    weekday = pd.Timestamp(target_date).day_name()
    comparable = daily[daily["weekday"] == weekday].sort_values("date_dt").tail(12)
    if len(comparable) >= 2:
        sample = comparable
        basis = f"{len(sample)} comparable {weekday}s"
    else:
        sample = daily.sort_values("date_dt").tail(28)
        if sample.empty:
            return None
        basis = f"last {len(sample)} available trading days"

    net_vals = sample["net_sales_gbp"].dropna()
    gross_vals = sample["gross_sales_gbp"].dropna()
    cover_vals = sample["covers"].dropna()
    return {
        "historical_net_median": float(net_vals.median()) if len(net_vals) else np.nan,
        "historical_gross_median": float(gross_vals.median()) if len(gross_vals) else np.nan,
        "historical_covers_median": float(cover_vals.median()) if len(cover_vals) else np.nan,
        "n": len(sample),
        "basis": basis,
    }


def estimate_avg_spend(history, location, target_date, revenue_basis, vat_rate):
    """Return an average spend per cover estimate for a matching weekday, if possible."""
    if history is None or history.empty or "covers" not in history.columns:
        return np.nan
    hist = history.copy()
    if location != "All locations":
        hist = hist[hist["location"].str.casefold() == location.casefold()]
    hist["date_dt"] = pd.to_datetime(hist["date"], errors="coerce")
    hist = hist.dropna(subset=["date_dt"])
    hist = hist[(hist["covers"].fillna(0) > 0)]
    hist["weekday"] = hist["date_dt"].dt.day_name()
    hist["spend"] = (
        hist["gross_sales_gbp"] if revenue_basis == "Gross (including VAT)"
        else hist["net_sales_gbp"]
    )
    target_weekday = pd.Timestamp(target_date).day_name()
    hist = hist[hist["weekday"] == target_weekday].sort_values("date_dt").tail(12)
    if hist.empty:
        return np.nan
    daily = hist.groupby(hist["date_dt"].dt.date).agg(
        spend=("spend", "sum"), covers=("covers", "max")
    )
    daily = daily[daily["covers"] > 0]
    if daily.empty:
        return np.nan
    return float((daily["spend"] / daily["covers"]).median())


# ----------------------------
# Header and setup
# ----------------------------
st.title("HANBAO Sales Forecasting Engine")
st.caption(
    "Enter revenue forecasts manually. The app calculates required covers "
    "and reports gross and net revenue automatically."
)

with st.sidebar:
    st.header("Forecast setup")
    location = st.selectbox("Location", ["All locations", "Worcester", "Birmingham"])
    start_date = st.date_input("First forecast date", value=date.today())
    trading_days = int(
        st.number_input("Number of forecast days", min_value=1, max_value=31, value=5, step=1)
    )
    vat_rate = st.number_input(
        "VAT rate (%)", min_value=0.0, max_value=100.0, value=20.0, step=0.5,
        help="Used to convert between gross revenue (including VAT) and net revenue (excluding VAT).",
    )
    revenue_basis = st.selectbox(
        "Manual forecast revenue is entered as",
        ["Gross (including VAT)", "Net (excluding VAT)"],
    )
    st.caption(
        "Average spend per cover must use the same VAT basis as the manual forecast."
    )

# ----------------------------
# Imports
# ----------------------------
st.header("1. Upload your menu and historical sales")
with st.expander("CSV uploads and templates", expanded=True):
    c1, c2 = st.columns(2)
    with c1:
        menu_upload = st.file_uploader("Menu CSV", type=["csv"], key="menu_upload")
        st.caption("Required menu columns: item, category, price_gbp.")
        st.download_button(
            "Download menu template",
            data=build_sample_menu().to_csv(index=False),
            file_name="hanbao_menu_template.csv",
            mime="text/csv",
        )
    with c2:
        history_upload = st.file_uploader(
            "Historical sales CSV", type=["csv"], key="history_upload"
        )
        st.caption(
            "Use the historical template for daily revenue, covers and optional item-level sales."
        )
        history_template = pd.DataFrame(
            columns=[
                "date", "location", "gross_sales_gbp", "net_sales_gbp", "covers",
                "transactions", "avg_spend_gross_gbp", "avg_spend_net_gbp",
                "item", "category", "quantity", "price_gbp",
                "food_cost_per_unit_gbp", "transaction_id",
            ]
        )
        st.download_button(
            "Download historical sales template",
            data=history_template.to_csv(index=False),
            file_name="hanbao_historical_sales_template.csv",
            mime="text/csv",
        )

menu_upload_df = load_csv(menu_upload)
if menu_upload_df is None:
    menu = build_sample_menu()
    st.warning(
        "The example menu is illustrative. Upload HANBAO's actual menu, prices and costs "
        "before using item-level estimates."
    )
else:
    menu = normalise_menu(menu_upload_df)
    if menu is None or menu.empty:
        st.error("The menu needs item, category and positive price_gbp values. Using example menu.")
        menu = build_sample_menu()

history_upload_df = load_csv(history_upload)
history = normalise_history(history_upload_df, vat_rate)
if history_upload is not None and (history is None or history.empty):
    st.error(
        "Could not find usable historical data. Include a date and at least one of "
        "gross_sales_gbp, net_sales_gbp, or quantity plus price_gbp."
    )

# ----------------------------
# Manual forecast and automatic covers
# ----------------------------
st.header("2. Enter your revenue forecast")
st.write(
    "Enter the revenue you expect for each day. Covers are calculated automatically as "
    "the forecast revenue divided by average spend per cover, rounded up to the next whole cover."
)

default_revenue = [2500, 3000, 5000, 6000, 3500]
rows = []
for i in range(trading_days):
    forecast_date = start_date + timedelta(days=i)
    suggested_spend = estimate_avg_spend(
        history, location, forecast_date, revenue_basis, vat_rate
    )
    if not np.isfinite(suggested_spend) or suggested_spend <= 0:
        suggested_spend = 25.0
    rows.append(
        {
            "Date": forecast_date,
            "Day": forecast_date.strftime("%A"),
            "Manual forecast revenue (£)": float(default_revenue[i % len(default_revenue)]),
            "Average spend per cover (£)": round(float(suggested_spend), 2),
        }
    )

forecast_input = st.data_editor(
    pd.DataFrame(rows),
    use_container_width=True,
    hide_index=True,
    disabled=["Date", "Day"],
    num_rows="fixed",
    column_config={
        "Manual forecast revenue (£)": st.column_config.NumberColumn(
            "Manual forecast revenue (£)", min_value=0.0, step=100.0, format="£%.2f"
        ),
        "Average spend per cover (£)": st.column_config.NumberColumn(
            "Average spend per cover (£)", min_value=0.01, step=1.0, format="£%.2f"
        ),
    },
    key="manual_forecast_editor",
)

forecast_input["Manual forecast revenue (£)"] = pd.to_numeric(
    forecast_input["Manual forecast revenue (£)"], errors="coerce"
).fillna(0).clip(lower=0)
forecast_input["Average spend per cover (£)"] = pd.to_numeric(
    forecast_input["Average spend per cover (£)"], errors="coerce"
).fillna(0).clip(lower=0)

factor = 1 + float(vat_rate) / 100
forecast_input["Covers forecast"] = np.where(
    forecast_input["Average spend per cover (£)"] > 0,
    np.ceil(
        forecast_input["Manual forecast revenue (£)"]
        / forecast_input["Average spend per cover (£)"]
    ),
    np.nan,
)
if revenue_basis == "Gross (including VAT)":
    forecast_input["Gross revenue forecast (£)"] = forecast_input["Manual forecast revenue (£)"]
    forecast_input["Net revenue forecast (£)"] = forecast_input["Gross revenue forecast (£)"] / factor
    forecast_input["Average spend gross (£)"] = forecast_input["Average spend per cover (£)"]
    forecast_input["Average spend net (£)"] = forecast_input["Average spend per cover (£)"] / factor
else:
    forecast_input["Net revenue forecast (£)"] = forecast_input["Manual forecast revenue (£)"]
    forecast_input["Gross revenue forecast (£)"] = forecast_input["Net revenue forecast (£)"] * factor
    forecast_input["Average spend net (£)"] = forecast_input["Average spend per cover (£)"]
    forecast_input["Average spend gross (£)"] = forecast_input["Average spend per cover (£)"] * factor

forecast_input["Gross less net (£)"] = (
    forecast_input["Gross revenue forecast (£)"] - forecast_input["Net revenue forecast (£)"]
)

# Historical comparisons are context only and never alter the manual forecast.
history_rows = []
for _, row in forecast_input.iterrows():
    hist = daily_history_summary(history, location, row["Date"])
    history_rows.append(hist or {})
if history is not None and not history.empty:
    forecast_input["Historical net median (£)"] = [
        r.get("historical_net_median", np.nan) for r in history_rows
    ]
    forecast_input["Historical gross median (£)"] = [
        r.get("historical_gross_median", np.nan) for r in history_rows
    ]
    forecast_input["Historical covers median"] = [
        r.get("historical_covers_median", np.nan) for r in history_rows
    ]
    forecast_input["Historical comparison basis"] = [
        r.get("basis", "No comparable history") for r in history_rows
    ]

# ----------------------------
# Dashboard
# ----------------------------
st.header("3. Revenue and covers dashboard")
total_manual = float(forecast_input["Manual forecast revenue (£)"].sum())
total_gross = float(forecast_input["Gross revenue forecast (£)"].sum())
total_net = float(forecast_input["Net revenue forecast (£)"].sum())
total_vat = total_gross - total_net
total_covers = int(forecast_input["Covers forecast"].fillna(0).sum())
avg_gross_spend = total_gross / total_covers if total_covers else 0
avg_net_spend = total_net / total_covers if total_covers else 0

k1, k2, k3, k4 = st.columns(4)
k1.metric("Forecast gross revenue", money(total_gross))
k2.metric("Forecast net revenue", money(total_net))
k3.metric("VAT element", money(total_vat))
k4.metric("Covers required", f"{total_covers:,}")

k5, k6 = st.columns(2)
k5.metric("Average gross spend per cover", money(avg_gross_spend))
k6.metric("Average net spend per cover", money(avg_net_spend))

st.caption(
    f"VAT conversion uses {vat_rate:.1f}%. Gross revenue includes the VAT element; "
    "net revenue excludes it. This calculation assumes the same VAT rate applies to all forecast sales."
)

display_cols = [
    "Date", "Day", "Manual forecast revenue (£)", "Gross revenue forecast (£)",
    "Net revenue forecast (£)", "Gross less net (£)", "Average spend per cover (£)",
    "Covers forecast",
]
if "Historical net median (£)" in forecast_input.columns:
    display_cols += [
        "Historical net median (£)", "Historical gross median (£)",
        "Historical covers median", "Historical comparison basis",
    ]
st.dataframe(
    forecast_input[display_cols],
    use_container_width=True,
    hide_index=True,
    column_config={
        "Manual forecast revenue (£)": st.column_config.NumberColumn(format="£%.2f"),
        "Gross revenue forecast (£)": st.column_config.NumberColumn(format="£%.2f"),
        "Net revenue forecast (£)": st.column_config.NumberColumn(format="£%.2f"),
        "Gross less net (£)": st.column_config.NumberColumn("VAT element (£)", format="£%.2f"),
        "Average spend per cover (£)": st.column_config.NumberColumn(format="£%.2f"),
        "Historical net median (£)": st.column_config.NumberColumn(format="£%.2f"),
        "Historical gross median (£)": st.column_config.NumberColumn(format="£%.2f"),
    },
)

# ----------------------------
# Menu demand and gross profit estimate
# ----------------------------
st.header("4. Menu demand and estimated gross profit")
st.caption(
    "This estimate allocates forecast net revenue using your menu revenue mix. "
    "It is not a basket-level prediction."
)

if "sales_mix_pct" not in menu:
    menu["sales_mix_pct"] = np.nan
if "food_cost_per_unit_gbp" not in menu:
    menu["food_cost_per_unit_gbp"] = np.nan

edited_menu = st.data_editor(
    menu,
    use_container_width=True,
    hide_index=True,
    num_rows="dynamic",
    column_config={
        "price_gbp": st.column_config.NumberColumn("Menu price (£)", min_value=0.01, format="£%.2f"),
        "sales_mix_pct": st.column_config.NumberColumn("Net revenue mix (%)", min_value=0.0, max_value=100.0, format="%.2f"),
        "food_cost_per_unit_gbp": st.column_config.NumberColumn("Food cost / unit (£)", min_value=0.0, format="£%.2f"),
    },
    key="menu_editor",
)
edited_menu = normalise_menu(edited_menu)
if edited_menu is None or edited_menu.empty:
    edited_menu = build_sample_menu()

mix_total = float(pd.to_numeric(edited_menu["sales_mix_pct"], errors="coerce").fillna(0).sum())
if abs(mix_total - 100) <= 0.05:
    menu_plan = edited_menu.copy()
    menu_plan["Estimated net revenue (£)"] = total_net * (
        pd.to_numeric(menu_plan["sales_mix_pct"], errors="coerce").fillna(0) / 100
    )
    menu_plan["Estimated units"] = np.ceil(
        menu_plan["Estimated net revenue (£)"] /
        pd.to_numeric(menu_plan["price_gbp"], errors="coerce").replace(0, np.nan)
    ).fillna(0).astype(int)
    menu_plan["Estimated net sales after rounding (£)"] = (
        menu_plan["Estimated units"] * menu_plan["price_gbp"]
    )
    menu_plan["Estimated food cost (£)"] = (
        menu_plan["Estimated units"]
        * pd.to_numeric(menu_plan["food_cost_per_unit_gbp"], errors="coerce").fillna(0)
    )
    menu_plan["Estimated gross profit (£)"] = (
        menu_plan["Estimated net sales after rounding (£)"] - menu_plan["Estimated food cost (£)"]
    )
    menu_plan["Estimated gross margin (%)"] = np.where(
        menu_plan["Estimated net sales after rounding (£)"] > 0,
        menu_plan["Estimated gross profit (£)"]
        / menu_plan["Estimated net sales after rounding (£)"] * 100,
        np.nan,
    )
    menu_cols = [
        "item", "category", "price_gbp", "sales_mix_pct", "Estimated net revenue (£)",
        "Estimated units", "Estimated net sales after rounding (£)",
        "food_cost_per_unit_gbp", "Estimated food cost (£)",
        "Estimated gross profit (£)", "Estimated gross margin (%)",
    ]
    st.dataframe(
        menu_plan[menu_cols],
        use_container_width=True,
        hide_index=True,
        column_config={
            "price_gbp": st.column_config.NumberColumn("Menu price (£)", format="£%.2f"),
            "sales_mix_pct": st.column_config.NumberColumn("Net revenue mix (%)", format="%.2f%%"),
            "Estimated net revenue (£)": st.column_config.NumberColumn(format="£%.2f"),
            "Estimated net sales after rounding (£)": st.column_config.NumberColumn(format="£%.2f"),
            "food_cost_per_unit_gbp": st.column_config.NumberColumn("Food cost / unit (£)", format="£%.2f"),
            "Estimated food cost (£)": st.column_config.NumberColumn(format="£%.2f"),
            "Estimated gross profit (£)": st.column_config.NumberColumn(format="£%.2f"),
            "Estimated gross margin (%)": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )
    m1, m2, m3 = st.columns(3)
    m1.metric("Estimated net menu sales", money(menu_plan["Estimated net sales after rounding (£)"].sum()))
    m2.metric("Estimated food cost", money(menu_plan["Estimated food cost (£)"].sum()))
    m3.metric("Estimated gross profit", money(menu_plan["Estimated gross profit (£)"].sum()))
    st.caption(
        "Gross profit here means estimated net sales minus the food cost entered for each item. "
        "It excludes labour, rent, utilities, payment fees and other operating costs. "
        "Missing food costs are treated as £0, which overstates profit."
    )
else:
    menu_plan = pd.DataFrame()
    st.warning(
        f"Menu revenue mix currently totals {mix_total:.2f}%. Set the mix to 100% to estimate item quantities and gross profit."
    )

# ----------------------------
# Export
# ----------------------------
st.header("5. Export your forecast")
excel_buffer = io.BytesIO()
with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
    forecast_input.to_excel(writer, index=False, sheet_name="Daily Forecast")
    edited_menu.to_excel(writer, index=False, sheet_name="Menu")
    if not menu_plan.empty:
        menu_plan.to_excel(writer, index=False, sheet_name="Menu Demand")

st.download_button(
    "Download forecast (Excel)",
    data=excel_buffer.getvalue(),
    file_name=f"hanbao_sales_forecast_{start_date.isoformat()}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
st.download_button(
    "Download daily forecast (CSV)",
    data=forecast_input.to_csv(index=False),
    file_name=f"hanbao_daily_forecast_{start_date.isoformat()}.csv",
    mime="text/csv",
)

with st.expander("Model assumptions and limitations"):
    st.markdown(
        """
        - Revenue is entered manually for each forecast date.
        - Covers are calculated as `ceil(manual forecast revenue / average spend per cover)`.
        - The average spend per cover must use the same VAT basis selected for the manual forecast.
        - Gross revenue includes VAT; net revenue excludes VAT. The configured VAT rate is applied uniformly to all forecast sales.
        - Historical sales provide comparison and, where possible, a suggested average spend per cover. They never overwrite the manual forecast.
        - Menu quantities are indicative, independently rounded estimates based on net revenue mix; they are not a basket-level forecast.
        - Estimated gross profit is net menu sales less entered food costs. It is not operating profit and excludes labour and overheads.
        - Confirm the VAT treatment of Tevalis exports and menu prices before relying on the outputs.
        """
    )
