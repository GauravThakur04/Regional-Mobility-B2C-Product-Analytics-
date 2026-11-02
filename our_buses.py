"""Our buses (ticket_ticketnew.source = 1): one enriched ticket frame and one journey frame.

Channel — how the ticket was booked:
  Green Card        ticket_with_pass = true (the card is the payment)
  App / Website     ticket_sourcing 2 / 1, paid online
  App (old system)  migrated 2021–2024 tickets (meta.from = 'oldest prod' / 'old prod')
"""
import os
import numpy as np
import pandas as pd
import metrics as M

CHANNELS = ["App", "Website", "Green Card", "App (old system)", "Other"]
KM_BANDS = [(0, 50, "Under 50 km"), (50, 100, "50–100 km"), (100, 150, "100–150 km"),
            (150, 250, "150–250 km"), (250, 10**6, "250+ km")]
KM_ORDER = [b[2] for b in KM_BANDS] + ["Unknown"]
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _km(t):
    g = pd.read_pickle(os.path.join(M.DATA, "04_town_coords.pkl"))
    a, b = g.reindex(t.from_town_id), g.reindex(t.to_town_id)
    la1, lo1, la2, lo2 = [np.radians(x.astype(float)) for x in (a.lat.values, a.lon.values, b.lat.values, b.lon.values)]
    h = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(h)) * 1.25          # road ≈ 1.25 × straight line


def build_tickets():
    t = M.build_tickets("source1")
    d = pd.read_pickle(os.path.join(M.DATA, "05_our_buses_detail.pkl")).drop(columns=["ticket_sourcing"])
    t = t.merge(d, on="ticket_id", how="left")
    legacy = t.meta_from.notna()
    t["era"] = np.where(legacy, "Old system (2021–24)", "Current app (2024 →)")
    t["channel"] = np.select(
        [t.service == M.GC, legacy, t.ticket_sourcing == 2, t.ticket_sourcing == 1],
        ["Green Card", "App (old system)", "App", "Website"], "Other")
    t["km"] = t.distance_in_km.where(t.distance_in_km > 0, _km(t))
    t["km_band"] = pd.Categorical(
        np.select([t.km.between(lo, hi, inclusive="left") for lo, hi, _ in KM_BANDS], [b[2] for b in KM_BANDS], "Unknown"),
        KM_ORDER, ordered=True)
    t["booked_at"] = pd.to_datetime(t.booked_at)
    t["lead_days"] = (t.journey_date - t.booked_at.dt.normalize()).dt.days
    t["book_hour"] = t.booked_at.dt.hour
    t["travel_dow"] = pd.Categorical(t.journey_date.dt.day_name().str[:3], DOW, ordered=True)
    t["operator"] = t.operator.str.strip().fillna("Unknown (old system)").where(~legacy, "Unknown (old system)")
    t["bus_has_machine"] = t.bus_has_machine.map({True: "Bus has ticket machine", False: "No machine"}).fillna("Unknown")
    return t


def build():
    t = build_tickets()
    j = M.build_journeys(t)
    return t, j
