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

LOCATIONS = [
    ("fridge", "🧊 Fridge"),
    ("freezer", "🥶 Freezer"),
    ("on_the_go", "🚗 On-the-go"),
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

def add_bag(location: str, dt_utc_iso: str, oz: float):
    sb().table("bags").insert(
        {"location": location, "dt": dt_utc_iso, "oz": oz, "used": False, "used_at": None}
    ).execute()

def set_used(bag_id: int, used: bool):
    payload = {"used": used, "used_at": datetime.now(tz=tz.UTC).isoformat() if used else None}
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
    totals = {}
    grand = 0.0
    for loc in LOC_KEYS:
        rows = fetch_bags(loc)
        loc_total = sum(float(b["oz"]) for b in rows if not b["used"])
        totals[loc] = loc_total
        grand += loc_total
    return totals, grand

# ------------------ Totals ------------------
totals, grand_total = totals_unused()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Fridge (unused oz)", f"{totals['fridge']:.1f}")
c2.metric("Freezer (unused oz)", f"{totals['freezer']:.1f}")
c3.metric("On-the-go (unused oz)", f"{totals['on_the_go']:.1f}")
c4.metric("Total (unused oz)", f"{grand_total:.1f}")

st.divider()

# ------------------ Add bag form ------------------
# Default time = "now" when you open the app, and after each successful add.
if "add_time" not in st.session_state:
    st.session_state["add_time"] = datetime.now().time().replace(second=0, microsecond=0)

with st.expander("➕ Add a bag", expanded=True):
    with st.form("add_bag_form", clear_on_submit=True):
        colA, colB, colC, colD = st.columns([1.4, 1, 1, 1])

        location = colA.selectbox("Location", LOC_KEYS, format_func=lambda k: LOC_LABEL[k], index=0)
        d = colB.date_input("Date", value=date.today())
        t = colC.time_input("Time", value=st.session_state["add_time"])
        oz = colD.number_input("Amount (oz)", min_value=0.1, step=0.5, value=3.0)

        if st.form_submit_button("Add bag"):
            dt_local = datetime.combine(d, t).replace(tzinfo=LOCAL_TZ)
            dt_utc = dt_local.astimezone(tz.UTC)
            add_bag(location, dt_utc.isoformat(), float(oz))

            # Reset time to now so the next add defaults to current time
            st.session_state["add_time"] = datetime.now().time().replace(second=0, microsecond=0)

            st.success("Added!")
            st.rerun()

st.divider()

# ------------------ Sections ------------------
cols = st.columns(3)

def render_section(container, location: str):
    container.subheader(LOC_LABEL[location])
    rows = fetch_bags(location)
    unused = [b for b in rows if not b["used"]]
    used = [b for b in rows if b["used"]]

    # Unused first (visible)
    if not unused:
        container.caption("No unused bags here.")
    else:
        for b in unused:
            bag_id = b["id"]
            label = f"{fmt_dt(b['dt'])} • {float(b['oz']):.1f} oz"

            c = container.columns([4.8, 1.9, 1.4, 1.2])
            c[0].markdown(f"**{label}**")

            # Move control: pick destination + click Move
            dest = c[1].selectbox(
                "Move to",
                LOC_KEYS,
                index=LOC_KEYS.index(b["location"]),
                format_func=lambda k: LOC_LABEL[k],
                key=f"move_sel_{bag_id}",
                label_visibility="collapsed",
            )
            if dest != b["location"]:
                if c[1].button("Move", key=f"move_btn_{bag_id}"):
                    move_bag(bag_id, dest)
                    st.rerun()

            if c[2].button("Used", key=f"use_{bag_id}"):
                set_used(bag_id, True)
                st.rerun()

            if c[3].button("Delete", key=f"del_{bag_id}"):
                delete_bag(bag_id)
                st.rerun()

    # Used section (hidden by default to reduce clutter)
    with container.expander(f"Used bags ({len(used)})", expanded=False):
        if not used:
            st.caption("None used yet.")
        else:
            for b in used:
                bag_id = b["id"]
                label = f"{fmt_dt(b['dt'])} • {float(b['oz']):.1f} oz"
                c = st.columns([5.2, 1.6, 1.2])

                c[0].markdown(f"✅ **{label}**")

                dest = c[1].selectbox(
                    "Move to",
                    LOC_KEYS,
                    index=LOC_KEYS.index(b["location"]),
                    format_func=lambda k: LOC_LABEL[k],
                    key=f"move_used_sel_{bag_id}",
                    label_visibility="collapsed",
                )
                if dest != b["location"]:
                    if c[1].button("Move", key=f"move_used_btn_{bag_id}"):
                        move_bag(bag_id, dest)
                        st.rerun()

                if c[2].button("Undo", key=f"undo_{bag_id}"):
                    set_used(bag_id, False)
                    st.rerun()

render_section(cols[0], "fridge")
render_section(cols[1], "freezer")
render_section(cols[2], "on_the_go")

st.caption("Backed by Supabase. Used bags are tucked away to reduce clutter.")
