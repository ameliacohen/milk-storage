import os
from datetime import datetime, date
import streamlit as st
from dateutil import tz
from supabase import create_client

# ------------------ Setup ------------------
st.set_page_config(page_title="Milk Tracker", page_icon="🍼", layout="wide")
st.title("🍼 Milk Storage Tracker")

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not url or not key:
    st.error("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY. Add them to Streamlit Secrets.")
    st.stop()

@st.cache_resource
def sb():
    return create_client(url, key)

LOCAL_TZ = tz.tzlocal()

# ------------------ Supabase helpers ------------------
def fetch_bags(location: str):
    res = (
        sb()
        .table("bags")
        .select("id, location, dt, oz, used")
        .eq("location", location)
        .order("dt", desc=True)
        .order("id", desc=True)
        .execute()
    )
    return res.data or []

def add_bag(location: str, dt_utc_iso: str, oz: float):
    sb().table("bags").insert(
        {"location": location, "dt": dt_utc_iso, "oz": oz, "used": False, "used_at": None}
    ).execute()

def set_used(bag_id: int, used: bool):
    payload = {"used": used, "used_at": datetime.now(tz=tz.UTC).isoformat() if used else None}
    sb().table("bags").update(payload).eq("id", bag_id).execute()

def delete_bag(bag_id: int):
    sb().table("bags").delete().eq("id", bag_id).execute()

def totals_unused():
    fridge = fetch_bags("fridge")
    freezer = fetch_bags("freezer")
    f_total = sum(float(b["oz"]) for b in fridge if not b["used"])
    z_total = sum(float(b["oz"]) for b in freezer if not b["used"])
    return f_total, z_total, f_total + z_total

def fmt_dt(dt_str: str) -> str:
    # Supabase returns ISO timestamps (often with Z). Convert to local time for display.
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00")).astimezone(LOCAL_TZ)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return dt_str

# ------------------ Totals ------------------
f_total, z_total, total = totals_unused()
c1, c2, c3 = st.columns(3)
c1.metric("Fridge (unused oz)", f"{f_total:.1f}")
c2.metric("Freezer (unused oz)", f"{z_total:.1f}")
c3.metric("Total (unused oz)", f"{total:.1f}")

st.divider()

# ------------------ Add bag form ------------------
with st.expander("➕ Add a bag", expanded=True):
    with st.form("add_bag_form", clear_on_submit=True):
        colA, colB, colC, colD = st.columns([1, 1, 1, 1])

        location = colA.selectbox("Location", ["fridge", "freezer"], index=0)
        d = colB.date_input("Date", value=date.today())
        t = colC.time_input("Time", value=datetime.now().time().replace(second=0, microsecond=0))
        oz = colD.number_input("Amount (oz)", min_value=0.1, step=0.5, value=3.0)

        if st.form_submit_button("Add bag"):
            # Interpret entered date/time as local time, then store in UTC.
            dt_local = datetime.combine(d, t).replace(tzinfo=LOCAL_TZ)
            dt_utc = dt_local.astimezone(tz.UTC)
            add_bag(location, dt_utc.isoformat(), float(oz))
            st.success("Added!")
            st.rerun()

st.divider()

# ------------------ Lists ------------------
left, right = st.columns(2)

def render_section(container, title: str, location: str):
    container.subheader(title)
    rows = fetch_bags(location)

    if not rows:
        container.caption("No bags yet.")
        return

    for b in rows:
        bag_id = b["id"]
        used = bool(b["used"])
        label = f"{fmt_dt(b['dt'])} • {float(b['oz']):.1f} oz"

        cols = container.columns([5, 1.5, 1.2])

        cols[0].markdown(
            f"**{label}**" + ("  \n✅ Used" if used else "")
        )

        if used:
            if cols[1].button("Undo", key=f"undo-{bag_id}"):
                set_used(bag_id, False)
                st.rerun()
        else:
            if cols[1].button("Mark used", key=f"use-{bag_id}"):
                set_used(bag_id, True)
                st.rerun()

        if cols[2].button("Delete", key=f"del-{bag_id}"):
            delete_bag(bag_id)
            st.rerun()

render_section(left, "🧊 Fridge", "fridge")
render_section(right, "🥶 Freezer", "freezer")

st.caption("Shared tracker backed by Supabase. Unused totals update automatically.")
