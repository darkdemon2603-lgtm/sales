import io
from datetime import date, timedelta
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="HANBAO Sales Target & Forecasting Engine", page_icon="🍔", layout="wide")

# ----------------------------
# Helpers
# ----------------------------
def money(value):
    try:
        return f"£{float(value):,.2f}"
    except (TypeError, ValueError):
        return "—"

def pct(value, decimals=1):
    try:
        return f"{float(value):,.{decimals}f}%"
    except (TypeError, ValueError):
        return "—"

def clean_columns(df):
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_").replace("-", "_") for c in df.columns]
    aliases = {
        "menu_item": "item", "product": "item", "product_name": "item",
        "selling_price": "price_gbp", "price": "price_gbp", "unit_price": "price_gbp",
        "units": "quantity", "qty": "quantity", "units_sold": "quantity",
        "sales": "net_sales_gbp", "net_sales": "net_sales_gbp", "revenue": "net_sales_gbp",
        "food_cost": "food_cost_per_unit_gbp", "unit_food_cost": "food_cost_per_unit_gbp",
        "transaction": "transaction_id", "order_id": "transaction_id",
        "venue": "location", "site": "location",
    }
    return df.rename(columns={c: aliases.get(c, c) for c in df.columns})

def parse_date_column(df, col="date"):
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
    return df

def safe_numeric(df, columns):
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

def load_csv(uploaded_file):
    if uploaded_file is None:
        return None
    try:
        return clean_columns(pd.read_csv(uploaded_file))
    except Exception as exc:
        st.error(f"Could not read {uploaded_file.name}: {exc}")
        return None

def normalise_menu(df):
    required = {"item", "category", "price_gbp"}
    if df is None or not required.issubset(df.columns):
        return None
    out = df.copy()
    out["item"] = out["item"].astype(str).str.strip()
    out["category"] = out["category"].astype(str).str.strip()
    out["price_gbp"] = pd.to_numeric(out["price_gbp"], errors="coerce")
    if "sales_mix_pct" not in out.columns:
        out["sales_mix_pct"] = np.nan
    out["sales_mix_pct"] = pd.to_numeric(out["sales_mix_pct"], errors="coerce")
    if "food_cost_per_unit_gbp" not in out.columns:
        out["food_cost_per_unit_gbp"] = np.nan
    out["food_cost_per_unit_gbp"] = pd.to_numeric(out["food_cost_per_unit_gbp"], errors="coerce")
    out = out.dropna(subset=["item", "category", "price_gbp"])
    out = out[out["price_gbp"] > 0]
    return out

def normalise_history(df):
    if df is None:
        return None
    required = {"date"}
    if not required.issubset(df.columns):
        return None
    out = parse_date_column(df)
    out = safe_numeric(out, ["quantity", "net_sales_gbp", "price_gbp", "food_cost_per_unit_gbp", "covers"])
    if "location" not in out.columns:
        out["location"] = "All locations"
    if "item" not in out.columns:
        out["item"] = "All items"
    if "category" not in out.columns:
        out["category"] = "Uncategorised"
    out["location"] = out["location"].fillna("All locations").astype(str)
    if "net_sales_gbp" not in out.columns and {"quantity", "price_gbp"}.issubset(out.columns):
        out["net_sales_gbp"] = out["quantity"] * out["price_gbp"]
    if "net_sales_gbp" not in out.columns:
        return None
    out["net_sales_gbp"] = pd.to_numeric(out["net_sales_gbp"], errors="coerce")
    out = out.dropna(subset=["date", "net_sales_gbp"])
    out = out[out["net_sales_gbp"] >= 0]
    return out

def daily_history_summary(history, location, target_date):
    if history is None or history.empty:
        return None
    hist = history.copy()
    if location != "All locations" and "location" in hist.columns:
        hist = hist[hist["location"].str.casefold() == location.casefold()]
    if hist.empty:
        return None
    hist["date"] = pd.to_datetime(hist["date"], errors="coerce")
    hist = hist.dropna(subset=["date"])
    hist["weekday"] = hist["date"].dt.day_name()
    target_weekday = pd.Timestamp(target_date).day_name()
    # Prefer the most recent 12 matching weekdays; fall back to all recent daily totals.
    daily = hist.groupby(hist["date"].dt.date, as_index=False)["net_sales_gbp"].sum()
    daily["date"] = pd.to_datetime(daily["date"])
    daily["weekday"] = daily["date"].dt.day_name()
    comparable = daily[daily["weekday"] == target_weekday].sort_values("date").tail(12)
    if len(comparable) >= 2:
        values = comparable["net_sales_gbp"].astype(float)
        return {
            "forecast": float(values.median()),
            "mean": float(values.mean()),
            "low": float(values.quantile(0.25)),
            "high": float(values.quantile(0.75)),
            "n": int(len(values)),
            "basis": f"{len(values)} comparable {target_weekday}s",
        }
    recent = daily.sort_values("date").tail(28)
    if recent.empty:
        return None
    values = recent["net_sales_gbp"].astype(float)
    return {
        "forecast": float(values.median()),
        "mean": float(values.mean()),
        "low": float(values.quantile(0.25)),
        "high": float(values.quantile(0.75)),
        "n": int(len(values)),
        "basis": f"last {len(values)} trading days (not enough matching weekdays)",
    }

def get_actual_mix(history, location=None, lookback_days=84):
    if history is None or history.empty or "item" not in history.columns:
        return None
    hist = history.copy()
    hist["date"] = pd.to_datetime(hist["date"], errors="coerce")
    hist = hist.dropna(subset=["date"])
    cutoff = pd.Timestamp.today().normalize() - pd.Timedelta(days=lookback_days)
    hist = hist[hist["date"] >= cutoff]
    if location and location != "All locations" and "location" in hist.columns:
        hist = hist[hist["location"].str.casefold() == location.casefold()]
    if hist.empty:
        return None
    mix = hist.groupby(["item", "category"], as_index=False)["net_sales_gbp"].sum()
    total = mix["net_sales_gbp"].sum()
    if total <= 0:
        return None
    mix["sales_mix_pct"] = mix["net_sales_gbp"] / total * 100
    return mix[["item", "category", "sales_mix_pct"]]

def build_sample_menu():
    return pd.DataFrame([
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
    ], columns=["item", "category", "price_gbp", "sales_mix_pct", "food_cost_per_unit_gbp"])

def make_daily_plan(targets, menu, average_spend, covers_forecast, history, location, start_date, vat_basis):
    rows = []
    for i, target in enumerate(targets):
        day_date = start_date + timedelta(days=i)
        hist = daily_history_summary(history, location, day_date)
        hist_forecast = hist["forecast"] if hist else None
        covers = float(covers_forecast[i])
        spend = float(average_spend[i])
        demand_forecast = covers * spend
        if hist_forecast is not None:
            # User-defined customer model drives forecast; historical revenue is shown as context, not silently blended.
            forecast = demand_forecast
            basis = hist["basis"]
        else:
            forecast = demand_forecast
            basis = "customer × average spend assumption"
        rows.append({
            "Date": day_date,
            "Day": day_date.strftime("%A"),
            "Target (£)": float(target),
            "Forecast (£)": forecast,
            "Gap (£)": forecast - float(target),
            "Covers forecast": int(round(covers)),
            "Average spend (£)": spend,
            "Historical median (£)": hist_forecast if hist_forecast is not None else np.nan,
            "Historical range low (£)": hist["low"] if hist else np.nan,
            "Historical range high (£)": hist["high"] if hist else np.nan,
            "Historical basis": basis,
        })
    return pd.DataFrame(rows)

# ----------------------------
# Header and guidance
# ----------------------------
st.title("HANBAO Sales Target & Forecasting Engine")
st.caption("Turn revenue targets into customer demand, realistic forecasts and measurable actions.")
st.info(
    "This is a planning model, not a guarantee of sales. Start with real POS data wherever possible. "
    "The included menu is illustrative and must be replaced before using the results operationally."
)

with st.sidebar:
    st.header("Planning setup")
    location = st.selectbox("Location", ["All locations", "Worcester", "Birmingham"])
    start_date = st.date_input("First trading day", value=date.today())
    trading_days = st.number_input("Trading days in this plan", min_value=1, max_value=14, value=5, step=1)
    st.markdown("---")
    st.subheader("Revenue basis")
    vat_basis = st.selectbox("Target basis", ["Net sales (excluding VAT)", "Gross sales (including VAT)"])
    st.caption("Keep targets, history and menu prices on a consistent VAT basis.")

# ----------------------------
# Data import
# ----------------------------
st.header("1. Bring in your actual data")
with st.expander("Upload files / download templates", expanded=True):
    c1, c2, c3 = st.columns(3)
    with c1:
        menu_upload = st.file_uploader("Menu CSV", type=["csv"], key="menu_upload")
        st.caption("Required columns: item, category, price_gbp. Optional: sales_mix_pct, food_cost_per_unit_gbp.")
    with c2:
        history_upload = st.file_uploader("Historical sales CSV", type=["csv"], key="history_upload")
        st.caption("Required: date and net_sales_gbp. Recommended: location, item, category, quantity, transaction_id, covers.")
    with c3:
        transaction_upload = st.file_uploader("Transaction / covers CSV (optional)", type=["csv"], key="transaction_upload")
        st.caption("Useful columns: date, location, transaction_id, covers, transaction_value_gbp.")
    st.download_button("Download menu template", data=build_sample_menu().to_csv(index=False), file_name="hanbao_menu_template.csv", mime="text/csv")
    history_template = pd.DataFrame(columns=["date", "location", "item", "category", "quantity", "price_gbp", "net_sales_gbp", "food_cost_per_unit_gbp", "transaction_id", "covers"])
    st.download_button("Download historical sales template", data=history_template.to_csv(index=False), file_name="hanbao_historical_sales_template.csv", mime="text/csv")

uploaded_menu = load_csv(menu_upload)
if uploaded_menu is None:
    menu_raw = build_sample_menu()
    st.warning("Using an illustrative menu. Upload HANBAO's real menu and prices before relying on the item-level outputs.")
else:
    menu_raw = uploaded_menu

menu = normalise_menu(menu_raw)
if menu is None or menu.empty:
    st.error("Menu file needs item, category and price_gbp columns, with positive prices. Using the example menu until corrected.")
    menu = build_sample_menu()

history_raw = load_csv(history_upload)
history = normalise_history(history_raw)
if history_upload is not None and (history is None or history.empty):
    st.error("Historical sales file needs a valid date column and net_sales_gbp, or quantity plus price_gbp.")

transactions = load_csv(transaction_upload)
if transactions is not None:
    transactions = parse_date_column(transactions)
    transactions = safe_numeric(transactions, ["covers", "transaction_value_gbp", "net_sales_gbp"])
    if "transaction_value_gbp" not in transactions.columns and "net_sales_gbp" in transactions.columns:
        transactions["transaction_value_gbp"] = transactions["net_sales_gbp"]

# ----------------------------
# Sales mix
# ----------------------------
st.header("2. Menu mix and item economics")
mix_source = st.radio("Menu mix source", ["Use menu assumptions", "Estimate from historical sales"], horizontal=True)
if mix_source == "Estimate from historical sales" and history is not None:
    actual_mix = get_actual_mix(history, location=location)
    if actual_mix is not None:
        menu = menu.drop(columns=["sales_mix_pct"], errors="ignore").merge(actual_mix, on=["item", "category"], how="left")
        menu["sales_mix_pct"] = menu["sales_mix_pct"].fillna(0)
        st.success("Revenue mix estimated from the uploaded sales history (last 84 days where available). Items not found in history receive 0%.")
    else:
        st.warning("Could not estimate mix from the history file. Using the menu assumptions instead.")

edited_menu = st.data_editor(
    menu,
    use_container_width=True,
    hide_index=True,
    num_rows="dynamic",
    column_config={
        "price_gbp": st.column_config.NumberColumn("Price (£)", min_value=0.01, format="£%.2f"),
        "sales_mix_pct": st.column_config.NumberColumn("Revenue mix (%)", min_value=0.0, max_value=100.0, format="%.2f%%"),
        "food_cost_per_unit_gbp": st.column_config.NumberColumn("Food cost / unit (£)", min_value=0.0, format="£%.2f"),
    },
)
edited_menu = normalise_menu(edited_menu)
mix_total = float(edited_menu["sales_mix_pct"].fillna(0).sum()) if edited_menu is not None and not edited_menu.empty else 0
if abs(mix_total - 100) <= 0.05:
    st.success(f"Revenue mix totals {mix_total:.2f}%.")
else:
    st.warning(f"Revenue mix currently totals {mix_total:.2f}%. Aim for 100% for item-level estimates.")
if edited_menu is None or edited_menu.empty:
    edited_menu = build_sample_menu()

# ----------------------------
# Targets and forecast assumptions
# ----------------------------
st.header("3. Set targets and forecast demand")
st.write("Enter each day's target, expected customer covers and average spend. If historical sales are uploaded, the app shows comparable-day performance alongside your forecast.")
default_targets = [2500, 3000, 5000, 6000, 3500]
default_covers = [100, 120, 200, 240, 140]
default_spend = [25, 25, 25, 25, 25]
day_rows = []
for i in range(int(trading_days)):
    d = start_date + timedelta(days=i)
    idx = i % len(default_targets)
    day_rows.append({
        "Date": d,
        "Day": d.strftime("%A"),
        "Target (£)": float(default_targets[idx]),
        "Forecast covers": int(default_covers[idx]),
        "Average spend (£)": float(default_spend[idx]),
    })
default_plan = pd.DataFrame(day_rows)
targets_editor = st.data_editor(
    default_plan,
    use_container_width=True,
    hide_index=True,
    disabled=["Date", "Day"],
    column_config={
        "Target (£)": st.column_config.NumberColumn("Target (£)", min_value=0.0, format="£%.2f"),
        "Forecast covers": st.column_config.NumberColumn("Forecast covers", min_value=0, step=1),
        "Average spend (£)": st.column_config.NumberColumn("Average spend (£)", min_value=0.0, format="£%.2f"),
    },
)
targets_editor["Target (£)"] = pd.to_numeric(targets_editor["Target (£)"], errors="coerce").fillna(0)
targets_editor["Forecast covers"] = pd.to_numeric(targets_editor["Forecast covers"], errors="coerce").fillna(0)
targets_editor["Average spend (£)"] = pd.to_numeric(targets_editor["Average spend (£)"], errors="coerce").fillna(0)
targets_editor["Forecast (£)"] = targets_editor["Forecast covers"] * targets_editor["Average spend (£)"]
targets_editor["Gap (£)"] = targets_editor["Forecast (£)"] - targets_editor["Target (£)"]
targets_editor["Covers needed at forecast spend"] = np.where(
    targets_editor["Average spend (£)"] > 0,
    np.ceil(targets_editor["Target (£)"] / targets_editor["Average spend (£)"]),
    np.nan
)
targets_editor["Extra covers needed"] = np.maximum(
    0, targets_editor["Covers needed at forecast spend"] - targets_editor["Forecast covers"]
)

# Historical comparison summary
if history is not None and not history.empty:
    hist_rows = []
    for _, row in targets_editor.iterrows():
        hist = daily_history_summary(history, location, row["Date"])
        hist_rows.append(hist["forecast"] if hist else np.nan)
    targets_editor["Historical median (£)"] = hist_rows
    targets_editor["Forecast vs historical (£)"] = targets_editor["Forecast (£)"] - targets_editor["Historical median (£)"]

# ----------------------------
# Dashboard KPIs
# ----------------------------
st.header("4. Forecast dashboard")
total_target = float(targets_editor["Target (£)"].sum())
total_forecast = float(targets_editor["Forecast (£)"].sum())
total_gap = total_forecast - total_target
total_covers = float(targets_editor["Forecast covers"].sum())
weighted_spend = total_forecast / total_covers if total_covers > 0 else 0
target_covers = float(np.ceil(total_target / weighted_spend)) if weighted_spend > 0 else 0
growth_needed = ((total_target / total_forecast) - 1) * 100 if total_forecast > 0 else np.nan

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Revenue target", money(total_target))
k2.metric("Forecast revenue", money(total_forecast), delta=money(total_gap))
k3.metric("Revenue gap", money(max(0, total_target - total_forecast)))
k4.metric("Forecast covers", f"{int(round(total_covers)):,}")
k5.metric("Average spend", money(weighted_spend))
st.caption(f"At the current weighted average spend, approximately {int(target_covers):,} covers are needed to reach the target. Forecast covers are {int(round(total_covers)):,}.")
if total_forecast >= total_target:
    st.success("The current customer × average-spend assumptions meet or exceed the revenue target. Check that the assumptions are supported by historical performance.")
else:
    st.error(f"The current assumptions are {money(total_target - total_forecast)} below target. Use the scenario planner and action plan below to close the gap.")

display_cols = ["Date", "Day", "Target (£)", "Forecast (£)", "Gap (£)", "Forecast covers", "Average spend (£)", "Covers needed at forecast spend", "Extra covers needed"]
if "Historical median (£)" in targets_editor.columns:
    display_cols += ["Historical median (£)", "Forecast vs historical (£)"]
st.dataframe(targets_editor[display_cols], use_container_width=True, hide_index=True)

# ----------------------------
# Scenario planner
# ----------------------------
st.header("5. Scenario planner")
st.write("Test the effect of changing customer numbers and average spend. Scenarios are assumptions, not guaranteed outcomes.")
base_covers = int(round(total_covers))
base_spend = weighted_spend
s1, s2 = st.columns(2)
with s1:
    conservative_covers_pct = st.slider("Conservative covers vs forecast (%)", min_value=-50, max_value=0, value=-15, step=5)
    conservative_spend_pct = st.slider("Conservative average spend vs forecast (%)", min_value=-30, max_value=0, value=-5, step=5)
with s2:
    stretch_covers_pct = st.slider("Stretch covers vs forecast (%)", min_value=0, max_value=50, value=15, step=5)
    stretch_spend_pct = st.slider("Stretch average spend vs forecast (%)", min_value=0, max_value=30, value=5, step=5)

scenarios = [
    ("Conservative", max(0, base_covers * (1 + conservative_covers_pct / 100)), max(0, base_spend * (1 + conservative_spend_pct / 100))),
    ("Expected", base_covers, base_spend),
    ("Stretch", max(0, base_covers * (1 + stretch_covers_pct / 100)), max(0, base_spend * (1 + stretch_spend_pct / 100))),
]
scenario_df = pd.DataFrame([
    {"Scenario": name, "Covers": int(round(covers)), "Average spend (£)": spend, "Forecast revenue (£)": covers * spend, "Gap vs target (£)": covers * spend - total_target}
    for name, covers, spend in scenarios
])
st.dataframe(scenario_df, use_container_width=True, hide_index=True, column_config={
    "Average spend (£)": st.column_config.NumberColumn(format="£%.2f"),
    "Forecast revenue (£)": st.column_config.NumberColumn(format="£%.2f"),
    "Gap vs target (£)": st.column_config.NumberColumn(format="£%.2f"),
})
st.bar_chart(scenario_df.set_index("Scenario")[["Forecast revenue (£)"]])
st.caption("For a reliable forecast, calibrate scenario ranges against historical variability rather than choosing arbitrary percentages.")

# ----------------------------
# Menu demand and profit
# ----------------------------
st.header("6. Menu demand and gross profit estimate")
if mix_total > 0 and abs(mix_total - 100) <= 0.05:
    menu_plan = edited_menu.copy()
    menu_plan["Estimated revenue (£)"] = total_target * menu_plan["sales_mix_pct"] / 100
    menu_plan["Estimated units"] = np.ceil(menu_plan["Estimated revenue (£)"] / menu_plan["price_gbp"]).astype(int)
    menu_plan["Planned revenue after rounding (£)"] = menu_plan["Estimated units"] * menu_plan["price_gbp"]
    menu_plan["Food cost estimate (£)"] = menu_plan["Estimated units"] * menu_plan["food_cost_per_unit_gbp"].fillna(0)
    menu_plan["Gross profit estimate (£)"] = menu_plan["Planned revenue after rounding (£)"] - menu_plan["Food cost estimate (£)"]
    menu_plan["Gross margin estimate (%)"] = np.where(
        menu_plan["Planned revenue after rounding (£)"] > 0,
        menu_plan["Gross profit estimate (£)"] / menu_plan["Planned revenue after rounding (£)"] * 100,
        np.nan
    )
    cols = ["item", "category", "price_gbp", "sales_mix_pct", "Estimated revenue (£)", "Estimated units", "Planned revenue after rounding (£)", "food_cost_per_unit_gbp", "Food cost estimate (£)", "Gross profit estimate (£)", "Gross margin estimate (%)"]
    st.dataframe(menu_plan[cols], use_container_width=True, hide_index=True, column_config={
        "price_gbp": st.column_config.NumberColumn("Price (£)", format="£%.2f"),
        "sales_mix_pct": st.column_config.NumberColumn("Revenue mix (%)", format="%.2f%%"),
        "Estimated revenue (£)": st.column_config.NumberColumn(format="£%.2f"),
        "Planned revenue after rounding (£)": st.column_config.NumberColumn(format="£%.2f"),
        "food_cost_per_unit_gbp": st.column_config.NumberColumn("Food cost / unit (£)", format="£%.2f"),
        "Food cost estimate (£)": st.column_config.NumberColumn(format="£%.2f"),
        "Gross profit estimate (£)": st.column_config.NumberColumn(format="£%.2f"),
        "Gross margin estimate (%)": st.column_config.NumberColumn(format="%.1f%%"),
    })
    estimated_sales = float(menu_plan["Planned revenue after rounding (£)"].sum())
    estimated_cost = float(menu_plan["Food cost estimate (£)"].sum())
    estimated_gp = float(menu_plan["Gross profit estimate (£)"].sum())
    m1, m2, m3 = st.columns(3)
    m1.metric("Rounded menu revenue", money(estimated_sales))
    m2.metric("Estimated food cost", money(estimated_cost))
    m3.metric("Estimated gross profit", money(estimated_gp))
    st.caption("This menu calculation distributes the full plan target using revenue mix. It is an indicative demand model, not an order-level basket forecast. Missing food costs are treated as £0, so profit will be overstated until costs are entered.")
else:
    st.warning("Enter a valid menu revenue mix totalling 100% to calculate item quantities. The customer-demand forecast above remains available.")

# ----------------------------
# Action plan
# ----------------------------
st.header("7. Action plan to close the gap")
gap_to_close = max(0, total_target - total_forecast)
st.write(f"Revenue gap to close: **{money(gap_to_close)}**. Add actions with an owner, deadline and an estimated impact. Treat impacts as hypotheses until measured.")
if "actions" not in st.session_state:
    st.session_state.actions = pd.DataFrame([
        {"Action": "Increase advance bookings", "Owner": "", "Deadline": start_date, "Expected incremental revenue (£)": 0.0, "Status": "Not started", "Actual incremental revenue (£)": 0.0},
        {"Action": "Improve drinks / sides attachment", "Owner": "", "Deadline": start_date, "Expected incremental revenue (£)": 0.0, "Status": "Not started", "Actual incremental revenue (£)": 0.0},
    ])
actions = st.data_editor(
    st.session_state.actions,
    use_container_width=True,
    hide_index=True,
    num_rows="dynamic",
    column_config={
        "Deadline": st.column_config.DateColumn("Deadline"),
        "Expected incremental revenue (£)": st.column_config.NumberColumn(min_value=0.0, format="£%.2f"),
        "Actual incremental revenue (£)": st.column_config.NumberColumn(min_value=0.0, format="£%.2f"),
        "Status": st.column_config.SelectboxColumn(options=["Not started", "In progress", "Complete", "Cancelled"]),
    },
    key="action_editor",
)
st.session_state.actions = actions
expected_impact = pd.to_numeric(actions.get("Expected incremental revenue (£)", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
actual_impact = pd.to_numeric(actions.get("Actual incremental revenue (£)", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
a1, a2, a3 = st.columns(3)
a1.metric("Expected action impact", money(expected_impact))
a2.metric("Actual action impact recorded", money(actual_impact))
a3.metric("Gap remaining after expected impact", money(max(0, gap_to_close - expected_impact)))
if expected_impact >= gap_to_close and gap_to_close > 0:
    st.success("The actions' estimated impact covers the current gap. Validate the estimates against results.")
elif gap_to_close > 0:
    st.warning(f"Current actions leave an estimated {money(gap_to_close - expected_impact)} gap.")
else:
    st.success("No revenue gap is currently forecast. Actions can focus on protecting performance or improving profitability.")

# ----------------------------
# Export
# ----------------------------
st.header("8. Export your plan")
export_buffer = io.BytesIO()
with pd.ExcelWriter(export_buffer, engine="openpyxl") as writer:
    targets_editor.to_excel(writer, index=False, sheet_name="Daily Forecast")
    scenario_df.to_excel(writer, index=False, sheet_name="Scenarios")
    edited_menu.to_excel(writer, index=False, sheet_name="Menu")
    actions.to_excel(writer, index=False, sheet_name="Action Plan")
st.download_button(
    "Download sales plan (Excel)",
    data=export_buffer.getvalue(),
    file_name=f"hanbao_sales_plan_{start_date.isoformat()}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
st.download_button(
    "Download daily forecast (CSV)",
    data=targets_editor.to_csv(index=False),
    file_name=f"hanbao_daily_forecast_{start_date.isoformat()}.csv",
    mime="text/csv",
)

with st.expander("Model assumptions and limitations"):
    st.markdown("""
    - Forecast revenue is calculated from forecast covers × average spend. Historical comparable-day revenue is displayed as context, not automatically blended into the forecast.
    - Historical comparison requires a `date` and `net_sales_gbp` column. Product-level analysis improves when `item`, `category`, `quantity`, and `location` are also supplied.
    - Revenue mix percentages are shares of revenue, not shares of units or orders.
    - Menu quantities are calculated independently by item and rounded up. This can cause planned revenue to exceed the target and does not represent real-world basket composition.
    - Gross profit estimates exclude labour, rent, utilities, payment fees, VAT adjustments and other operating costs. Missing food costs are treated as zero and will overstate profit.
    - Use consistent sales definitions across targets, POS exports and menu prices. Do not mix VAT-inclusive and VAT-exclusive figures.
    - No causal marketing uplift is assumed. Enter expected campaign impact as a hypothesis and compare it with actual results.
    """)
