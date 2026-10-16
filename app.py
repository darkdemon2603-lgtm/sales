import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.set_page_config(page_title="HANBAO Weekly Sales Planner", layout="wide")
st.title("HANBAO | Wednesday–Sunday Sales Planner")
st.caption("Set a sales target for each trading day and calculate the quantity of each menu item to sell.")

DEFAULT_MENU = pd.DataFrame([
    {"item": "Cheeseburger", "category": "Burgers", "price_gbp": 10.50, "sales_mix_pct": 25.0},
    {"item": "Double Burger", "category": "Burgers", "price_gbp": 13.50, "sales_mix_pct": 15.0},
    {"item": "Chicken Burger", "category": "Burgers", "price_gbp": 12.50, "sales_mix_pct": 12.0},
    {"item": "Vegan Burger", "category": "Burgers", "price_gbp": 12.00, "sales_mix_pct": 5.0},
    {"item": "Fries", "category": "Sides", "price_gbp": 4.50, "sales_mix_pct": 15.0},
    {"item": "Loaded Fries", "category": "Sides", "price_gbp": 7.00, "sales_mix_pct": 8.0},
    {"item": "Chicken Tenders", "category": "Sides", "price_gbp": 7.50, "sales_mix_pct": 6.0},
    {"item": "Soft Drink", "category": "Drinks", "price_gbp": 3.00, "sales_mix_pct": 10.0},
    {"item": "Milkshake", "category": "Drinks", "price_gbp": 5.50, "sales_mix_pct": 2.0},
    {"item": "Dessert", "category": "Desserts", "price_gbp": 6.00, "sales_mix_pct": 2.0},
])

st.info(
    "The example menu and sales mix below are placeholders. Replace them with HANBAO's actual menu, "
    "prices and sales mix. Sales mix means the share of total revenue you want each item to contribute."
)

with st.sidebar:
    st.header("Weekly targets")
    targets = {}
    default_targets = {"Wednesday": 2500.0, "Thursday": 3000.0, "Friday": 5000.0,
                       "Saturday": 6000.0, "Sunday": 3500.0}
    for day in ["Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
        targets[day] = st.number_input(
            f"{day} sales target (£)", min_value=0.0,
            value=default_targets[day], step=250.0, key=f"target_{day}"
        )
    st.divider()
    st.header("Planning options")
    buffer_pct = st.slider("Extra target buffer (%)", 0, 25, 0)
    rounding_mode = st.selectbox(
        "Quantity rounding",
        ["Round up to reach target", "Closest to target"],
        help="Round up avoids falling below the target, but can overshoot."
    )

st.subheader("1. Enter your menu and expected sales mix")
st.write(
    "Edit the example rows, add your real products, and set the percentage of revenue expected from each item. "
    "The percentages should total 100%."
)

menu_upload = st.file_uploader(
    "Optional: upload your menu CSV (columns: item, category, price_gbp, sales_mix_pct)",
    type=["csv"]
)
if menu_upload is not None:
    try:
        menu = pd.read_csv(menu_upload)
        required_cols = {"item", "category", "price_gbp", "sales_mix_pct"}
        if not required_cols.issubset(menu.columns):
            st.error("Menu CSV needs columns: item, category, price_gbp, sales_mix_pct.")
            menu = DEFAULT_MENU.copy()
        else:
            menu = menu[["item", "category", "price_gbp", "sales_mix_pct"]].copy()
    except Exception as exc:
        st.error(f"Couldn't read menu CSV: {exc}")
        menu = DEFAULT_MENU.copy()
else:
    menu = DEFAULT_MENU.copy()

edited_menu = st.data_editor(
    menu,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "item": st.column_config.TextColumn("Menu item", required=True),
        "category": st.column_config.SelectboxColumn(
            "Category", options=["Burgers", "Sides", "Drinks", "Desserts", "Other"]
        ),
        "price_gbp": st.column_config.NumberColumn("Selling price (£)", min_value=0.01, step=0.50, format="£%.2f"),
        "sales_mix_pct": st.column_config.NumberColumn("Revenue mix (%)", min_value=0.0, max_value=100.0, step=1.0, format="%.1f%%")
    },
    key="menu_editor"
)

# Clean and validate menu data
menu = edited_menu.copy()
menu["item"] = menu["item"].fillna("").astype(str).str.strip()
menu["category"] = menu["category"].fillna("Other").astype(str)
menu["price_gbp"] = pd.to_numeric(menu["price_gbp"], errors="coerce")
menu["sales_mix_pct"] = pd.to_numeric(menu["sales_mix_pct"], errors="coerce")
menu = menu[
    (menu["item"] != "") &
    menu["price_gbp"].notna() &
    (menu["price_gbp"] > 0) &
    menu["sales_mix_pct"].notna() &
    (menu["sales_mix_pct"] >= 0)
].copy()

mix_total = float(menu["sales_mix_pct"].sum()) if not menu.empty else 0.0
if menu.empty:
    st.error("Add at least one menu item with a valid price and sales mix.")
    st.stop()
if not np.isclose(mix_total, 100.0, atol=0.2):
    st.warning(f"Your sales mix currently totals {mix_total:.1f}%. Adjust it to 100% for accurate targets.")
    if mix_total <= 0:
        st.stop()
        # If non-zero but not 100, normalize for calculations while clearly warning.
        # This permits the user to explore before finalizing the percentages.
else:
    st.success("Sales mix totals 100%.")

# Normalize mix to 100% for calculations, so totals still work if user is experimenting.
menu["mix_normalized_pct"] = menu["sales_mix_pct"] / mix_total * 100 if mix_total > 0 else 0
menu["target_revenue_share"] = menu["mix_normalized_pct"] / 100

st.subheader("2. Daily item quantities")
days = ["Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
all_daily = []
summary_rows = []

for day in days:
    target = targets[day] * (1 + buffer_pct / 100)
    if target <= 0:
        continue

    calc = menu[["item", "category", "price_gbp", "mix_normalized_pct", "target_revenue_share"]].copy()
    calc["day"] = day
    calc["daily_sales_target_gbp"] = target
    calc["item_revenue_target_gbp"] = target * calc["target_revenue_share"]
    raw_qty = calc["item_revenue_target_gbp"] / calc["price_gbp"]

    if rounding_mode == "Round up to reach target":
        calc["units_to_sell"] = np.ceil(raw_qty).astype(int)
    else:
        calc["units_to_sell"] = np.maximum(0, np.rint(raw_qty)).astype(int)

    calc["planned_item_revenue_gbp"] = calc["units_to_sell"] * calc["price_gbp"]
    calc["planned_total_revenue_gbp"] = calc["planned_item_revenue_gbp"].sum()
    calc["planned_item_revenue_share_pct"] = np.where(
        calc["planned_total_revenue_gbp"] > 0,
        calc["planned_item_revenue_gbp"] / calc["planned_total_revenue_gbp"] * 100,
        0
    )
    all_daily.append(calc)

    planned_rev = float(calc["planned_item_revenue_gbp"].sum())
    summary_rows.append({
        "Day": day,
        "Sales target (£)": target,
        "Planned sales (£)": planned_rev,
        "Above target (£)": planned_rev - target,
        "Total item units": int(calc["units_to_sell"].sum()),
    })

if not all_daily:
    st.info("Enter a sales target above £0 for at least one day.")
else:
    detail = pd.concat(all_daily, ignore_index=True)
    summary = pd.DataFrame(summary_rows)

    total_target = float(summary["Sales target (£)"].sum())
    total_planned = float(summary["Planned sales (£)"].sum())
    total_units = int(summary["Total item units"].sum())

    m1, m2, m3 = st.columns(3)
    m1.metric("Weekly target", f"£{total_target:,.2f}")
    m2.metric("Planned sales after rounding", f"£{total_planned:,.2f}",
              delta=f"£{total_planned - total_target:,.2f} vs target")
    m3.metric("Total item units to sell", f"{total_units:,}")

    st.dataframe(
        summary.style.format({
            "Sales target (£)": "£{:,.2f}",
            "Planned sales (£)": "£{:,.2f}",
            "Above target (£)": "£{:,.2f}",
            "Total item units": "{:,.0f}"
        }),
        use_container_width=True,
        hide_index=True
    )

    st.subheader("Daily breakdown")
    for day in days:
        day_data = detail[detail["day"] == day].copy()
        if day_data.empty:
            continue
        day_target = float(day_data["daily_sales_target_gbp"].iloc[0])
        day_planned = float(day_data["planned_item_revenue_gbp"].sum())
        with st.expander(
            f"{day} — target £{day_target:,.0f} | planned £{day_planned:,.2f} | "
            f"{int(day_data['units_to_sell'].sum())} units",
            expanded=(day == "Wednesday")
        ):
            view = day_data[[
                "item", "category", "price_gbp", "mix_normalized_pct",
                "item_revenue_target_gbp", "units_to_sell", "planned_item_revenue_gbp"
            ]].rename(columns={
                "item": "Menu item",
                "category": "Category",
                "price_gbp": "Price (£)",
                "mix_normalized_pct": "Revenue mix (%)",
                "item_revenue_target_gbp": "Revenue allocation (£)",
                "units_to_sell": "Units to sell",
                "planned_item_revenue_gbp": "Planned revenue (£)"
            })
            st.dataframe(
                view.style.format({
                    "Price (£)": "£{:.2f}",
                    "Revenue mix (%)": "{:.1f}%",
                    "Revenue allocation (£)": "£{:,.2f}",
                    "Units to sell": "{:,.0f}",
                    "Planned revenue (£)": "£{:,.2f}"
                }),
                use_container_width=True,
                hide_index=True
            )

    st.subheader("3. Export your plan")
    csv_data = detail[[
        "day", "item", "category", "price_gbp", "mix_normalized_pct",
        "daily_sales_target_gbp", "item_revenue_target_gbp",
        "units_to_sell", "planned_item_revenue_gbp"
    ]].rename(columns={
        "day": "day",
        "item": "menu_item",
        "category": "category",
        "price_gbp": "price_gbp",
        "mix_normalized_pct": "revenue_mix_pct",
        "daily_sales_target_gbp": "daily_target_gbp",
        "item_revenue_target_gbp": "item_revenue_allocation_gbp",
        "units_to_sell": "units_to_sell",
        "planned_item_revenue_gbp": "planned_revenue_gbp"
    })
    st.download_button(
        "Download item targets CSV",
        data=csv_data.to_csv(index=False).encode("utf-8"),
        file_name="hanbao_wednesday_sunday_item_targets.csv",
        mime="text/csv"
    )

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Weekly Summary", index=False)
        csv_data.to_excel(writer, sheet_name="Item Targets", index=False)
        menu.to_excel(writer, sheet_name="Menu & Mix", index=False)
    st.download_button(
        "Download Excel workbook",
        data=output.getvalue(),
        file_name="hanbao_wednesday_sunday_sales_plan.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

st.caption(
    "Method: each day's revenue target is allocated across menu items using the chosen revenue mix. "
    "Units are calculated as allocated revenue ÷ item price, then rounded according to your setting. "
    "This is a sales-mix plan, not a demand forecast; use actual POS mix data for more realistic quantities. "
    "Because individual items have different prices, the rounded plan may exceed the exact target."
)
