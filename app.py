import streamlit as st
import pandas as pd
import os
import glob
from datetime import datetime
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from utils.data_processing import (
    load_transactions, save_excel_data, load_members,
    add_transaction, add_member, generate_report_data, restore_backup
)
from utils.audit_logger import load_audit_log
import plotly.express as px

st.set_page_config(
    page_title="Royal Family Report Auto-Generator", layout="wide")

# ---------- 🔐 Simple Admin Lock ----------
st.sidebar.title("🔐 Admin Access")
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
ADMIN_PASSWORD = "royal123"

if not st.session_state.authenticated:
    pw = st.sidebar.text_input("Enter Admin Password", type="password")
    if st.sidebar.button("Unlock Admin Mode"):
        if pw == ADMIN_PASSWORD:
            st.session_state.authenticated = True
            st.sidebar.success("✅ Admin Mode Activated")
        else:
            st.sidebar.error("❌ Incorrect password")
else:
    st.sidebar.success("🟢 Admin Mode Active")
    if st.sidebar.button("Lock"):
        st.session_state.authenticated = False
        st.sidebar.warning("🔒 Admin Mode Locked")

# ---------- Sidebar report dates ----------
st.sidebar.header("Report Settings")
start_date = st.sidebar.date_input(
    "Start Date", datetime(datetime.now().year, 1, 1))
end_date = st.sidebar.date_input("End Date", datetime.now())
generate_btn = st.sidebar.button("Generate Report for Date Range")

# ---------- Tabs ----------
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "📥 Transactions", "👤 Members", "💰 MMF & Interest",
    "📊 Dashboard", "📄 Export Report", "🧾 Data Summary",
    "🧭 Restore Backups", "📜 Audit Log"
])

# ---------- Transactions ----------
with tab1:
    st.subheader("📥 Manage Transactions")
    if not st.session_state.authenticated:
        st.warning("🔒 Admin access required to edit.")
        st.dataframe(load_transactions(), use_container_width=True)
    else:
        df = load_transactions()
        if not df.empty:
            gb = GridOptionsBuilder.from_dataframe(df)
            gb.configure_pagination(
                enabled=True, paginationAutoPageSize=False, paginationPageSize=10)
            gb.configure_default_column(editable=True, groupable=True)
            gb.configure_selection('single', use_checkbox=True)
            grid = gb.build()
            grid_response = AgGrid(df, gridOptions=grid,
                                   update_mode=GridUpdateMode.VALUE_CHANGED,
                                   height=400, theme="alpine")
            edited_df = grid_response["data"]
            selected = grid_response["selected_rows"]
            c1, c2, c3 = st.columns(3)
            if c1.button("💾 Save Changes"):
                save_excel_data("data/transactions.xlsx", edited_df)
                st.success("Saved.")
            if c2.button("❌ Delete Selected") and selected:
                to_delete = selected[0]
                edited_df = edited_df[edited_df["Date"] != to_delete["Date"]]
                save_excel_data("data/transactions.xlsx", edited_df)
                st.success("Deleted row.")
        else:
            st.info("No transactions yet.")
        st.divider()
        st.subheader("➕ Add Transaction")
        mems = load_members()
        names = mems["Member"].tolist() if not mems.empty else []
        with st.form("txn_form"):
            date = st.date_input("Date", datetime.now())
            m = st.selectbox("Member", names)
            t = st.selectbox(
                "Type", ["Deposit", "Withdrawal", "Charge", "Interest", "MMF Transfer"])
            amt = st.number_input("Amount", min_value=0.0, step=100.0)
            cmt = st.text_input("Comment (optional)")
            sub = st.form_submit_button("Add")
        if sub:
            add_transaction(date, m, t, amt, cmt)
            st.success("Added.")

# ---------- Members ----------
with tab2:
    st.subheader("👤 Manage Members")
    if not st.session_state.authenticated:
        st.warning("🔒 Admin access required.")
        st.dataframe(load_members(), use_container_width=True)
    else:
        mems = load_members()
        if not mems.empty:
            gb = GridOptionsBuilder.from_dataframe(mems)
            gb.configure_default_column(editable=True)
            grid = gb.build()
            grid_response = AgGrid(mems, gridOptions=grid,
                                   update_mode=GridUpdateMode.VALUE_CHANGED,
                                   height=300, theme="alpine")
            edited = grid_response["data"]
            c1, c2 = st.columns(2)
            if c1.button("💾 Save Changes"):
                save_excel_data("data/members.xlsx", edited)
                st.success("Saved.")
            if c2.button("➕ Add New Member"):
                st.session_state.adding = True
        else:
            st.info("No members yet.")
        if st.session_state.get("adding", False):
            with st.form("add_member"):
                n = st.text_input("Name")
                t = st.number_input("Target", min_value=0.0, step=1000.0)
                addb = st.form_submit_button("Add")
            if addb and n:
                add_member(n, t)
                st.success("Added.")
                st.session_state.adding = False

# ---------- Dashboard ----------
with tab4:
    st.subheader("📊 Dashboard")
    df = load_transactions()
    if df.empty:
        st.info("No data.")
    else:
        df["Date"] = pd.to_datetime(df["Date"])
        df = df[(df["Date"] >= pd.to_datetime(start_date))
                & (df["Date"] <= pd.to_datetime(end_date))]
        df["Month"] = df["Date"].dt.strftime("%b %Y")
        col1, col2 = st.columns(2)
        dep = df[df["Type"] == "Deposit"].groupby(
            "Member")["Amount"].sum().reset_index()
        fig1 = px.bar(dep, x="Member", y="Amount",
                      title="Total Deposits by Member")
        col1.plotly_chart(fig1, use_container_width=True)
        pivot = df.pivot_table(index="Month", columns="Type",
                               values="Amount", aggfunc="sum", fill_value=0)
        pivot["Net Flow"] = pivot.get("Deposit", 0)-pivot.get("Withdrawal", 0)
        fig2 = px.line(pivot, x=pivot.index, y="Net Flow",
                       title="Monthly Net Flow", markers=True)
        col2.plotly_chart(fig2, use_container_width=True)

# ---------- Export Report ----------
with tab5:
    st.subheader("📄 Export Report")
    from utils.pdf_generator import create_pdf_report
    if generate_btn:
        summary = generate_report_data(
            start_date=start_date, end_date=end_date)
        pdf = create_pdf_report(
            summary, start_date=start_date, end_date=end_date)
        with open(pdf, "rb") as f:
            st.download_button("📥 Download PDF", f,
                               file_name=os.path.basename(pdf))
        st.success(f"Report created: {pdf}")

# ---------- Data Summary ----------
with tab6:
    st.subheader("🧾 Data Summary")
    st.dataframe(load_transactions(), use_container_width=True)
    st.dataframe(load_members(), use_container_width=True)
    with st.expander("Backups"):
        backups = sorted(glob.glob("backups/*.xlsx"), reverse=True)
        for f in backups:
            st.write(os.path.basename(f))

# ---------- Restore ----------
with tab7:
    st.subheader("🧭 Restore Backups")
    if not st.session_state.authenticated:
        st.warning("🔒 Admin access required.")
    else:
        files = sorted(glob.glob("backups/*.xlsx"), reverse=True)
        if files:
            names = [os.path.basename(f) for f in files]
            sel = st.selectbox("Select backup", names)
            if st.button("Restore Selected"):
                restore_backup(sel)
                st.success(f"Restored {sel}")
        else:
            st.info("No backups yet.")

# ---------- Audit Log ----------
with tab8:
    st.subheader("📜 Audit Trail")
    if not st.session_state.authenticated:
        st.warning("🔒 Admin access required.")
    else:
        logs = load_audit_log()
        st.dataframe(logs.sort_values(
            "Timestamp", ascending=False), use_container_width=True)
