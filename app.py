import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, timedelta

st.set_page_config(page_title="HANBAO Customer & Sales Planner", layout="wide")
st.title("HANBAO | Sales Target → Customers Required")
st.caption("Reverse-plan revenue into required customer visits, estimated unique customers, and new customers to attract.")

with st.sidebar:
    st.header("Sales target")
    target_revenue = st.number_input("Target revenue (£)", min_value=0.0, value=90000.0, step=5000.0)
    period_days = st.number_input("Trading days in period", min_value=1, max_value=366, value=30)
    average_spend = st.number_input("Average spend per customer visit (£)", min_value=0.01, value=25.0, step=1.0)
    st.divider()
    st.header("Customer behaviour")
    repeat_visit_share = st.slider("Share of visits from returning customers (%)", 0, 95, 30) / 100
    visits_per_returning_customer = st.number_input(
        "Average visits per returning customer during this period",
        min_value=1.0, max_value=100.0, value=2.0, step=0.5
    )
    current_customer_visits = st.number_input(
        "Expected customer visits already secured (optional)",
        min_value=0, value=0, step=100
    )
    safety_buffer = st.slider("Planning buffer (%)", 0, 30, 10) / 100

target_with_buffer = target_revenue * (1 + safety_buffer)
required_visits = int(np.ceil(target_with_buffer / average_spend))
visits_gap = max(0, required_visits - int(current_customer_visits))
daily_visits = required_visits / period_days
returning_visits = int(round(required_visits * repeat_visit_share))
new_customer_visits = max(0, required_visits - returning_visits)
unique_returning_customers = int(np.ceil(returning_visits / visits_per_returning_customer))
estimated_unique_customers = unique_returning_customers + new_customer_visits

st.subheader("Your target")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Revenue target incl. buffer", f"£{target_with_buffer:,.0f}")
c2.metric("Customer visits required", f"{required_visits:,}")
c3.metric("Visits per trading day", f"{daily_visits:,.0f}")
c4.metric("Estimated unique customers", f"{estimated_unique_customers:,}")

st.info("Revenue is driven by visits × average spend. Unique customers are estimated separately from repeat-visit assumptions; treat this as a planning estimate.")

st.subheader("Customer breakdown")
b1, b2, b3 = st.columns(3)
b1.metric("Visits from returning customers", f"{returning_visits:,}")
b2.metric("Visits from new / one-time customers", f"{new_customer_visits:,}")
b3.metric("Estimated unique returning customers", f"{unique_returning_customers:,}")

st.subheader("Daily planning")
start_date = st.date_input("Plan start date", value=date.today())
dates = [start_date + timedelta(days=i) for i in range(int(period_days))]
plan = pd.DataFrame({"date": pd.to_datetime(dates)})
plan["day"] = plan["date"].dt.day_name()
plan["weight"] = np.where(plan["day"].isin(["Friday", "Saturday", "Sunday"]), 1.25, 0.85)
plan["weight"] = plan["weight"] / plan["weight"].sum()
plan["revenue_target_gbp"] = (target_with_buffer * plan["weight"]).round(2)
plan["customer_visits_target"] = np.ceil(required_visits * plan["weight"]).astype(int)
st.dataframe(plan, use_container_width=True, hide_index=True)
st.download_button("Download daily plan CSV", plan.to_csv(index=False).encode("utf-8"),
                   file_name="hanbao_daily_customer_targets.csv", mime="text/csv")

st.divider()
st.subheader("Use actual sales data")
st.write("Upload a transaction-level CSV. A customer ID column is needed to count unique customers and repeat visits.")
uploaded = st.file_uploader("Upload sales CSV", type=["csv"], key="actual_sales")
if uploaded is not None:
    try:
        actual = pd.read_csv(uploaded)
        actual.columns = actual.columns.str.strip()
        st.write("Detected columns:", ", ".join(actual.columns.astype(str)))

        def find_col(candidates):
            lower_map = {str(c).strip().lower(): c for c in actual.columns}
            for candidate in candidates:
                if candidate in lower_map:
                    return lower_map[candidate]
            return None

        revenue_col = find_col(["revenue", "sales", "total", "order_total", "amount", "net_sales"])
        customer_col = find_col(["customer_id", "customerid", "customer", "guest_id", "email"])
        order_col = find_col(["order_id", "orderid", "transaction_id", "ticket_id"])
        date_col = find_col(["date", "order_date", "created_at", "transaction_date"])

        if revenue_col is None:
            st.error("Couldn't identify a revenue column. Rename it to 'revenue' or edit the candidate list in app.py.")
        else:
            actual[revenue_col] = pd.to_numeric(actual[revenue_col], errors="coerce")
            valid = actual.dropna(subset=[revenue_col]).copy()
            if order_col:
                order_revenue = valid.groupby(order_col, dropna=False)[revenue_col].sum()
                order_count = len(order_revenue)
                total_revenue = float(order_revenue.sum())
                avg_order_value = total_revenue / order_count if order_count else 0
            else:
                order_count = len(valid)
                total_revenue = float(valid[revenue_col].sum())
                avg_order_value = total_revenue / order_count if order_count else 0

            m1, m2, m3 = st.columns(3)
            m1.metric("Historical revenue", f"£{total_revenue:,.2f}")
            m2.metric("Transactions / orders", f"{order_count:,}")
            m3.metric("Average order value", f"£{avg_order_value:,.2f}")

            if customer_col:
                st.metric("Unique identified customers", f"{valid[customer_col].nunique(dropna=True):,}")
                if order_col:
                    pairs = valid[[customer_col, order_col]].dropna().drop_duplicates()
                    visits_per_customer = pairs.groupby(customer_col)[order_col].nunique()
                    st.metric("Customers with 2+ orders", f"{int((visits_per_customer > 1).sum()):,}")
            else:
                st.warning("No customer ID found. Unique customers and repeat behaviour cannot be measured reliably.")

            if date_col:
                valid[date_col] = pd.to_datetime(valid[date_col], errors="coerce")
                daily = valid.dropna(subset=[date_col]).groupby(valid[date_col].dt.date)[revenue_col].sum()
                if not daily.empty:
                    st.write("Historical daily revenue")
                    st.line_chart(daily)
    except Exception as e:
        st.error(f"Could not analyse CSV: {type(e).__name__}: {e}")

st.caption("This is a target-planning calculator, not an automatic demand prediction. For better forecasts, use several months of daily sales, trading days, promotions, bookings, spend, and reliable customer IDs.")
