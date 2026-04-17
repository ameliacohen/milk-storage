import os
from datetime import datetime, date
import streamlit as st
from zoneinfo import ZoneInfo
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

LOCAL_TZ = ZoneInfo("America/Los_Angeles")
UTC_TZ = ZoneInfo("UTC")

LOCATIONS = [
    ("freezer", "🥶 Freezer"),
]
LOC_LABEL = {k: v for k, v in LOCATIONS}
LOC_KEYS = [k for k, _ in LOCATIONS]

# ------------------ DB helpers ------------------
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

def fetch_all_bags():
    res = (
        sb()
        .table("bags")
        .select("id, location, dt, oz, used")
        .order("dt", desc=True)
        .execute()
    )
    return res.data or []

def add_bag(location: str, dt_utc_iso: str, oz: float):
    sb().table("bags").insert(
        {"location": location, "dt": dt_utc_iso, "oz": oz, "used": False, "used_at": None}
    ).execute()

def set_used(bag_id: int, used: bool):
    payload = {"used": used, "used_at": datetime.now(UTC_TZ).isoformat() if used else None}
    sb().table("bags").update(payload).eq("id", bag_id).execute()

def delete_bag(bag_id: int):
    sb().table("bags").delete().eq("id", bag_id).execute()

def move_bag(bag_id: int, new_location: str):
    sb().table("bags").update({"location": new_location}).eq("id", bag_id).execute()

def fmt_dt(dt_str: str) -> str:
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00")).astimezone(LOCAL_TZ)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return dt_str

def totals_unused():
    rows = fetch_bags("freezer")
    total = sum(float(b["oz"]) for b in rows if not b["used"])
    return total

def daily_totals():
    rows = fetch_all_bags()
    by_day = {}

    for b in rows:
        dt = datetime.fromisoformat(b["dt"].replace("Z", "+00:00")).astimezone(LOCAL_TZ)
        day = dt.date()

        if day not in by_day:
            by_day[day] = {"total": 0.0, "used": 0.0, "unused": 0.0}

        oz = float(b["oz"])
        by_day[day]["total"] += oz

        if b["used"]:
            by_day[day]["used"] += oz
        else:
            by_day[day]["unused"] += oz

    return sorted(by_day.items(), reverse=True)

# ------------------ Totals ------------------
total_unused = totals_unused()

c1, c2 = st.columns(2)
c1.metric("Freezer (unused oz)", f"{total_unused:.1f}")
c2.metric("Total (unused oz)", f"{total_unused:.1f}")

st.divider()

# ------------------ Daily Tracker ------------------
st.subheader("📊 Daily Totals")

daily = daily_totals()

if not daily:
    st.caption("No data yet.")
else:
    for day, vals in daily:
        cols = st.columns(4)
        cols[0].markdown(f"**{day}**")
        cols[1].metric("Total", f"{vals['total']:.1f} oz")
        cols[2].metric("Used", f"{vals['used']:.1f} oz")
        cols[3].metric("Unused", f"{vals['unused']:.1f} oz")

st.divider()

# ------------------ Add bag form ------------------
if "add_time" not in st.session_state:
    st.session_state["add_time"] = datetime.now(LOCAL_TZ).time().replace(second=0, microsecond=0)

with st.expander("➕ Add a bag", expanded=True):
    with st.form("add_bag_form", clear_on_submit=True):
        colA, colB, colC, colD = st.columns([1.4, 1, 1, 1])

        location = colA.selectbox("Location", LOC_KEYS, format_func=lambda k: LOC_LABEL[k], index=0)
        d = colB.date_input("Date", value=date.today())
        t = colC.time_input("Time", value=st.session_state["add_time"])
        oz = colD.number_input("Amount (oz)", min_value=0.1, step=0.5, value=3.0)

        if st.form_submit_button("Add bag"):
            dt_local = datetime.combine(d, t).replace(tzinfo=LOCAL_TZ)
            dt_utc = dt_local.astimezone(UTC_TZ)
            add_bag(location, dt_utc.isoformat(), float(oz))

            st.session_state["add_time"] = datetime.now(LOCAL_TZ).time().replace(second=0, microsecond=0)

            st.success("Added!")
            st.rerun()

st.divider()

# ------------------ Freezer Section ------------------
def render_section(container, location: str):
    container.subheader(LOC_LABEL[location])
    rows = fetch_bags(location)

    unused = [b for b in rows if not b["used"]]
    used = [b for b in rows if b["used"]]

    if not unused:
        container.caption("No unused bags.")
    else:
        for b in unused:
            bag_id = b["id"]
            label = f"{fmt_dt(b['dt'])} • {float(b['oz']):.1f} oz"

            col1, col2, col3 = container.columns([5, 1.2, 1.2])

            col1.markdown(f"**{label}**")

            if col2.button("Use", key=f"use_{bag_id}"):
                set_used(bag_id, True)
                st.rerun()

            if col3.button("Delete", key=f"del_{bag_id}"):
                delete_bag(bag_id)
                st.rerun()

    with container.expander(f"Used bags ({len(used)})", expanded=False):
        if not used:
            st.caption("None used yet.")
        else:
            for b in used:
                bag_id = b["id"]
                label = f"{fmt_dt(b['dt'])} • {float(b['oz']):.1f} oz"

                col1, col2 = st.columns([5, 1.2])

                col1.markdown(f"✅ **{label}**")

                if col2.button("Undo", key=f"undo_{bag_id}"):
                    set_used(bag_id, False)
                    st.rerun()

render_section(st, "freezer")

st.caption("Used bags are tucked away to reduce clutter.")
