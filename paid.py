"""Our buses, paid tickets: ticket_ticketnew.source = 1 AND is_paid = true, not cancelled, no test users.
Builds a ticket frame and a de-duplicated journey frame in the shape metrics.py expects."""
import os
import numpy as np
import pandas as pd
import metrics as M

NO_TOWN = "No town data (Dec-2021 → May-2022)"
CHANNELS = {1: "Website", 2: "App", 3: "Agent"}     # ticket_sourcing; 4 is a tiny test-like group → "Other"


def _clean(s):
    return s.astype("string").str.replace(r"\s+", " ", regex=True).str.strip().str.title()


def build_tickets():
    M.set_scope("paid")
    M.UNMAPPED_LEGACY = NO_TOWN
    t = pd.read_pickle(os.path.join(M.DATA, "06_our_buses_paid.pkl"))
    bus = pd.read_pickle(os.path.join(M.DATA, "05_our_buses_detail.pkl"))[["ticket_id", "bus_number", "operator"]]
    t = t.merge(bus.drop_duplicates("ticket_id"), on="ticket_id", how="left")
    t["bus"] = t.bus_number.fillna("").str.upper().str.replace(r"[^A-Z0-9]", "", regex=True).replace("", "Not recorded")
    t["operator"] = t.operator.fillna("Not recorded")
    lk = pd.read_pickle(os.path.join(M.DATA, "03_state_lookup.pkl"))
    lk = lk[(lk.n_states == 1) & lk.district_key.notna() & (lk.district_key != "")].set_index("district_key").state_name

    t["journey_date"] = pd.to_datetime(t.journey_date)
    t["booking_date"] = pd.to_datetime(t.booking_date)
    t["valid"] = (t.status == 1) & ~t.is_deleted & ~t.is_test_user & ~t.is_test_ticket & t.journey_date.notna()
    t["completed"] = t.valid & (t.journey_date < M.AS_OF)
    t["service"] = np.where(t.pass_id.notna() | t.ticket_with_pass, M.GC, M.LR)
    t["channel"] = t.ticket_sourcing.map(CHANNELS).fillna("Other")
    t["booked_via"] = np.where(t.service == M.GC, t.channel + " + Green Card", t.channel)
    t["era"] = t.meta_from.map({"oldest prod": "2021–22 (no towns)", "old prod": "2022–24 (towns recovered)",
                                "old_ticket_ticket": "2024 (old table)"}).fillna("2024 → (current app)")

    has_town = t.from_town_id.notna() & t.to_town_id.notna()
    for side in ("from", "to"):
        dist = t[f"{side}_district"].str.strip()
        st = t[f"{side}_state_raw"].str.strip().fillna(dist.str.lower().map(lk))
        t[f"{side}_state"] = st.where(has_town, NO_TOWN).fillna(M.UNMAPPED)
        t[f"{side}_town"] = _clean(t[f"{side}_town"]).where(has_town, NO_TOWN).astype(object)
        d = _clean(dist)
        t[f"{side}_region"] = (d + " (" + t[f"{side}_state"] + ")").where(d.notna() & has_town, t[f"{side}_state"]).astype(object)

    for col in ("boarding_stop_raw", "drop_stop_raw"):
        t[col] = t[col].str.replace(r"\+?\d[\d\s-]{8,}\d", "[phone removed]", regex=True)
    t["boarding_stop"] = t.boarding_stop_raw.map(M._norm_stop)
    t["drop_stop"] = t.drop_stop_raw.map(M._norm_stop)
    t["origin_stop"] = (t.from_town + " · " + t.boarding_stop.fillna("(stop not recorded)")).where(has_town, NO_TOWN)
    t["dest_stop"] = (t.to_town + " · " + t.drop_stop.fillna("(stop not recorded)")).where(has_town, NO_TOWN)
    t["town_route"] = (t.from_town + " → " + t.to_town).where(has_town, NO_TOWN)
    t["stop_route"] = (t.origin_stop + " → " + t.dest_stop).where(has_town, NO_TOWN)
    t["region_route"] = (t.from_region + " → " + t.to_region).where(has_town, NO_TOWN)
    t["state_route"] = t.from_state + " → " + t.to_state

    la1, lo1, la2, lo2 = [np.radians(t[c].astype(float)) for c in ("from_lat", "from_lon", "to_lat", "to_lon")]
    h = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    t["km"] = t.distance_in_km.where(t.distance_in_km > 0, 6371 * 2 * np.arcsin(np.sqrt(h)) * 1.25)
    return t


def phones():
    """customer_key → phone for app & website customers (local data/ only)."""
    return pd.read_pickle(os.path.join(M.DATA, "25_app_customer_phones.pkl"))


def build():
    t = build_tickets()
    j = M.build_journeys(t)
    return t, j


if __name__ == "__main__":
    t, j = build()
    c = j[j.completed]
    print("valid tickets", int(t.valid.sum()), "| journeys", len(j), "| completed", len(c), "| people", c.customer_key.nunique())
    print("with towns:", int((c.town_route != NO_TOWN).sum()), "trips", c[c.town_route != NO_TOWN].customer_key.nunique(), "people")
    print(c.groupby("service").agg(trips=("customer_key", "size"), people=("customer_key", "nunique")))
    print(c[c.town_route != NO_TOWN].town_route.value_counts().head(10))
