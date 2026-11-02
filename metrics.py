"""Shared metric definitions. Used by the analysis scripts (full exports) and app.py (filtered
dashboard), so the dashboard and the exported tables always compute numbers the same way."""
import os, re
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

AS_OF = pd.Timestamp("2026-10-28")          # analysis date; journeys before this are "completed"
LAST_FULL_MONTH = pd.Period("2026-09", "M")  # Oct-2026 is partial and is excluded from retention cells
RECENCY_DAYS = 90                            # ~p85 of gaps between a repeat customer's trips
REGULAR_MIN_MONTHS = 3                       # regular = travelled in >= 3 distinct calendar months
ROUTE_REGULAR_MIN_TRIPS = 3                  # route-regular = >= 3 journeys on the same directed route
HIGH_FREQ_MIN = 6

SOURCE_NAMES = {1: "Direct operators", 4: "Booth agents", 6: "RSRTC", 8: "ITS (private OTA)",
                9: "Mentis (private OTA)", 10: "Bitla (private OTA)"}
LR, GC = "Long-route", "Green Card"
UNMAPPED_LEGACY = "Unmapped (legacy ticket)"
UNMAPPED = "Unmapped"

SCOPES = {
    "all": dict(title="All B2C bookings", lr_label="Long-route"),
    # Our own buses: book online (web/app, paid online) or with the Green Card, which is itself the
    # payment, so a Green Card booking counts even though is_paid stays false.
    "source1": dict(title="Our buses (source 1)", lr_label="App / Web"),
    # Our buses, paid tickets only (source = 1 AND is_paid): split by whether the Green Card pass was applied.
    "paid": dict(title="Our buses — paid tickets", lr_label="Without Green Card"),
}

FREQ_BANDS = [(1, 1, "One-time (1)"), (2, 2, "Occasional (2)"), (3, 5, "Repeat (3–5)"),
              (6, 10, "Frequent (6–10)"), (11, 10**9, "Highly frequent (11+)")]
FREQ_ORDER = [b[2] for b in FREQ_BANDS]


def set_scope(scope):
    global LR
    LR = SCOPES[scope]["lr_label"]


def _norm_stop(s):
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return None
    s = re.sub(r"\s+", " ", str(s)).strip(" ,.-")
    return s.title() if s else None


# --------------------------------------------------------------------------- build
def build_tickets(scope="all"):
    """Ticket-level frame with validity flags, service, states, regions and normalised stops."""
    set_scope(scope)
    t = pd.read_pickle(os.path.join(DATA, "01_tickets.pkl"))
    if scope == "source1":
        t = t[t.source == 1].copy()
    lk = pd.read_pickle(os.path.join(DATA, "03_state_lookup.pkl"))
    lk = lk[(lk.n_states == 1) & lk.district_key.notna() & (lk.district_key != "")].set_index("district_key").state_name

    t["no_user"] = t.customer_key.isna()
    t["customer_key"] = t.customer_key.fillna("nouser" + t.ticket_id.astype(str))
    t["journey_date"] = pd.to_datetime(t.journey_date)
    t["booking_date"] = pd.to_datetime(t.booking_date)
    t["is_test_ticket"] = t.is_test_ticket.fillna(False).astype(bool)
    t["service"] = np.where(t.ticket_with_pass.fillna(False).astype(bool), GC, LR)
    # status=1 is set when checkout starts; only is_paid=True rows were confirmed by the supplier
    # (RSRTC/Bitla confirm_booking_status=1) — unpaid rows are abandoned checkouts.
    t["attempt"] = (t.status == 1) & ~t.is_deleted & ~t.is_test_ticket & ~t.is_test_user & t.journey_date.notna()
    t["valid"] = t.attempt & t.is_paid.fillna(False).astype(bool)
    if scope == "source1":
        t["valid"] = t.valid | (t.attempt & (t.service == GC))
    t["completed"] = t.valid & (t.journey_date < AS_OF)
    t["channel"] = t.source.map(SOURCE_NAMES).fillna("Other")

    for side in ("from", "to"):
        raw = t[f"{side}_state_raw"].str.strip()
        by_district = t[f"{side}_district"].str.strip().str.lower().map(lk)
        st = raw.fillna(by_district).where(t[f"{side}_town_id"].notna())
        st = st.where(st.notna(), np.where(t[f"{side}_town_id"].isna(), UNMAPPED_LEGACY, UNMAPPED))
        t[f"{side}_state"] = st
        t[f"{side}_town"] = t[f"{side}_town"].str.strip().where(t[f"{side}_town_id"].notna(), UNMAPPED_LEGACY)
        # Region = district (state). District names repeat across states, so the state is kept in the label.
        dist = t[f"{side}_district"].str.strip().str.title()
        t[f"{side}_region"] = (dist + " (" + st + ")").where(dist.notna(), st)

    # Some operators put a contact number in the stop name; never carry phone numbers downstream.
    for col in ("boarding_stop_raw", "drop_stop_raw"):
        t[col] = t[col].str.replace(r"\+?\d[\d\s-]{8,}\d", "[phone removed]", regex=True)
    t["boarding_stop"] = t.boarding_stop_raw.map(_norm_stop)
    t["drop_stop"] = t.drop_stop_raw.map(_norm_stop)
    t["origin_stop"] = t.from_town + " · " + t.boarding_stop.fillna("(stop not recorded)")
    t["dest_stop"] = t.to_town + " · " + t.drop_stop.fillna("(stop not recorded)")
    legacy = t.from_town_id.isna() | t.to_town_id.isna()
    t.loc[legacy, ["origin_stop", "dest_stop"]] = UNMAPPED_LEGACY
    t["town_route"] = (t.from_town + " → " + t.to_town).where(~legacy, UNMAPPED_LEGACY)
    t["stop_route"] = (t.origin_stop + " → " + t.dest_stop).where(~legacy, UNMAPPED_LEGACY)
    t["state_route"] = t.from_state + " → " + t.to_state
    t["region_route"] = t.from_region + " → " + t.to_region
    return t


def build_journeys(t):
    """Deduplicate valid tickets into journeys: one customer, one travel date, one service, one
    directed town pair. Multiple tickets in the same key (re-bookings / split bookings) are one
    journey. Legacy tickets without towns are deduplicated on the ticket itself."""
    v = t[t.valid].copy()
    v["_svc_rank"] = (v.service != GC).astype(int)          # keep the Green Card ticket if mixed
    key_from = v.from_town_id.astype("Int64").astype(str)
    key_to = v.to_town_id.astype("Int64").astype(str)
    legacy = v.from_town_id.isna() | v.to_town_id.isna()
    v["journey_key"] = np.where(
        legacy, "t" + v.ticket_id.astype(str),
        v.customer_key + "|" + v.journey_date.dt.strftime("%Y-%m-%d") + "|" + key_from + "|" + key_to
        + "|" + v.service_id.fillna("").astype(str))
    v = v.sort_values(["journey_key", "_svc_rank", "ticket_id"])
    v["tickets_in_journey"] = v.groupby("journey_key").ticket_id.transform("size")
    j = v.drop_duplicates("journey_key").drop(columns="_svc_rank")
    j["month"] = j.journey_date.dt.to_period("M")
    return j


# --------------------------------------------------------------------------- helpers
def _mnum(p):
    """Period[M] series -> integer month number, for vectorised month differences."""
    return p.dt.year * 12 + p.dt.month


def freq_band(n):
    for lo, hi, lab in FREQ_BANDS:
        if lo <= n <= hi:
            return lab
    return None


def customer_profile(j):
    """One row per customer from completed journeys."""
    c = j[j.completed].assign(_lr=lambda d: d.service == LR, _gc=lambda d: d.service == GC)
    g = c.groupby("customer_key")
    primary = (c.groupby(["customer_key", "from_state"]).size().rename("n").reset_index()
               .sort_values(["customer_key", "n", "from_state"], ascending=[True, False, True])
               .drop_duplicates("customer_key").set_index("customer_key").from_state)
    prof = pd.DataFrame({
        "journeys": g.size(),
        "first_journey": g.journey_date.min(),
        "last_journey": g.journey_date.max(),
        "active_months": g.month.nunique(),
        "lr_journeys": g._lr.sum(),
        "gc_journeys": g._gc.sum(),
        "primary_boarding_state": primary,
    })
    prof["frequency_band"] = pd.Categorical(prof.journeys.map(freq_band), FREQ_ORDER, ordered=True)
    prof["is_repeat"] = prof.journeys >= 2
    prof["is_regular"] = prof.active_months >= REGULAR_MIN_MONTHS
    prof["services"] = np.select([(prof.lr_journeys > 0) & (prof.gc_journeys > 0), prof.gc_journeys > 0],
                                 ["Both", "Green Card only"], f"{LR} only")
    prof["segment"] = segment(prof)
    return prof


SEGMENT_ORDER = ["New (first trip ≤90d)", "Active – high frequency (6+)", "Active – other",
                 "Previously regular – inactive", "Inactive – low frequency (1–2)", "Inactive – other"]


def segment(prof):
    cut = AS_OF - pd.Timedelta(days=RECENCY_DAYS)
    recent = prof.last_journey >= cut
    new = prof.first_journey >= cut
    return pd.Categorical(np.select(
        [new, recent & (prof.journeys >= HIGH_FREQ_MIN), recent,
         ~recent & (prof.is_regular | (prof.journeys >= HIGH_FREQ_MIN)), ~recent & (prof.journeys <= 2)],
        SEGMENT_ORDER[:5], SEGMENT_ORDER[5]), SEGMENT_ORDER, ordered=True)


# --------------------------------------------------------------------------- tables
def overview(t, j, passes=None, registered=None):
    v = t[t.valid]
    c = j[j.completed]
    lr = set(c.customer_key[c.service == LR]); gc = set(c.customer_key[c.service == GC])
    rows = [
        ("Registered customers in database (distinct phone, non-test)", registered),
        ("Customers with ≥1 completed journey", len(lr | gc)),
        (f"{LR} customers", len(lr)),
        ("Green Card customers (used card on a completed journey)", len(gc)),
        ("Customers using both services", len(lr & gc)),
        (f"{LR} only", len(lr - gc)),
        ("Green Card only", len(gc - lr)),
        ("Total unique customers across both services", len(lr | gc)),
        ("Valid tickets (confirmed & paid, non-test, incl. upcoming)", len(v)),
        ("Abandoned checkouts (status=1 but never paid/confirmed) — not counted as bookings",
         int((t.attempt & ~t.valid).sum())),
        ("Customers with an abandoned checkout but no valid booking ever",
         len(set(t.customer_key[t.attempt & ~t.valid]) - set(v.customer_key))),
        ("Valid journeys after de-duplication (incl. upcoming)", len(j)),
        ("Completed journeys (journey date before as-of date)", len(c)),
        ("Upcoming journeys (journey date on/after as-of date)", int((~j.completed).sum())),
        ("Distinct directed town-to-town routes (mapped)", c.loc[c.town_route != UNMAPPED_LEGACY, "town_route"].nunique()),
        ("Distinct directed stop-to-stop routes (mapped)", c.loc[c.stop_route != UNMAPPED_LEGACY, "stop_route"].nunique()),
        ("Repeat customers (≥2 completed journeys)", int((c.groupby("customer_key").size() >= 2).sum())),
        ("Regular customers (active ≥3 distinct months)", int((c.groupby("customer_key").month.nunique() >= REGULAR_MIN_MONTHS).sum())),
        ("First completed journey", c.journey_date.min().date() if len(c) else None),
        ("Last completed journey", c.journey_date.max().date() if len(c) else None),
    ]
    if passes is not None:
        p = passes[passes.is_paid & ~passes.is_deleted & ~passes.is_test_user]
        rows += [("Green Card purchases (paid pass records)", len(p)),
                 ("Green Card holders (customers with a paid pass)", p.customer_key.nunique())]
    return pd.DataFrame(rows, columns=["metric", "value"])


def state_table(j, side="from", level="state"):
    c = j[j.completed]
    st = f"{side}_{level}"
    out = []
    for s, g in c.groupby(st):
        per = g.groupby("customer_key")
        n = per.size()
        months = per.month.nunique()
        svc = per.service.agg(lambda x: set(x))
        top = g.town_route[g.town_route != UNMAPPED_LEGACY].value_counts()
        out.append({
            "state": s,
            "unique_customers": len(n),
            "long_route_customers": int(svc.map(lambda x: LR in x).sum()),
            "green_card_customers": int(svc.map(lambda x: GC in x).sum()),
            "both_services_customers": int(svc.map(lambda x: len(x) == 2).sum()),
            "valid_tickets": int(g.tickets_in_journey.sum()),
            "completed_journeys": len(g),
            "repeat_customers": int((n >= 2).sum()),
            "regular_customers": int((months >= REGULAR_MIN_MONTHS).sum()),
            "repeat_customer_pct": round(100 * (n >= 2).mean(), 1),
            "avg_journeys_per_customer": round(n.mean(), 2),
            "most_popular_route": top.index[0] if len(top) else None,
            "most_popular_route_journeys": int(top.iat[0]) if len(top) else 0,
            "latest_activity": g.journey_date.max().date(),
        })
    col = ("boarding_" if side == "from" else "destination_") + level
    return pd.DataFrame(out).rename(columns={"state": col}).sort_values("unique_customers", ascending=False)


def route_table(j, level="town", min_customers=1):
    """Directed route table. level='town' (A town → B town) or 'stop' (town·stop → town·stop)."""
    c = j[j.completed & (j.town_route != UNMAPPED_LEGACY)]
    key = "town_route" if level == "town" else "stop_route"
    o, d = ("from_town", "to_town") if level == "town" else ("origin_stop", "dest_stop")
    per = c.groupby([key, "customer_key"]).size().rename("n").reset_index()
    cust = per.groupby(key).agg(unique_customers=("n", "size"),
                                repeat_customers=("n", lambda x: int((x >= 2).sum())),
                                route_regular_customers=("n", lambda x: int((x >= ROUTE_REGULAR_MIN_TRIPS).sum())))
    g = c.groupby(key)
    base = pd.DataFrame({
        "origin_state": g.from_state.first(), "origin": g[o].first(),
        "destination_state": g.to_state.first(), "destination": g[d].first(),
        "valid_tickets": g.tickets_in_journey.sum(), "completed_journeys": g.size(),
        "long_route_journeys": g.service.apply(lambda s: int((s == LR).sum())),
        "green_card_journeys": g.service.apply(lambda s: int((s == GC).sum())),
        "most_recent_journey": g.journey_date.max().dt.date,
    })
    if level == "stop":
        base["boarding_stop_raw_examples"] = g.boarding_stop_raw.agg(lambda s: " | ".join(sorted(set(s.dropna().astype(str)))[:3]))
        base["drop_stop_raw_examples"] = g.drop_stop_raw.agg(lambda s: " | ".join(sorted(set(s.dropna().astype(str)))[:3]))
    r = base.join(cust)
    r["avg_trips_per_customer"] = (r.completed_journeys / r.unique_customers).round(2)
    r["repeat_customer_pct"] = (100 * r.repeat_customers / r.unique_customers).round(1)
    r["repeat_booking_rate_pct"] = (100 * (1 - r.unique_customers / r.completed_journeys)).round(1)
    r = r[r.unique_customers >= min_customers].sort_values("completed_journeys", ascending=False)
    return r.reset_index().rename(columns={key: "route"})


def state_route_matrix(j, level="state"):
    """Directed origin × destination matrix at state or region (district) level."""
    o, d = f"from_{level}", f"to_{level}"
    c = j[j.completed & (j.from_state != UNMAPPED_LEGACY)]
    per = c.groupby([o, d, "customer_key"]).size().rename("n").reset_index()
    m = per.groupby([o, d]).agg(unique_customers=("n", "size"),
                                repeat_customers=("n", lambda x: int((x >= 2).sum())),
                                regular_customers=("n", lambda x: int((x >= ROUTE_REGULAR_MIN_TRIPS).sum())),
                                journeys=("n", "sum")).reset_index()
    m["repeat_customer_pct"] = (100 * m.repeat_customers / m.unique_customers).round(1)
    m["avg_trips_per_customer"] = (m.journeys / m.unique_customers).round(2)
    return m.rename(columns={o: f"origin_{level}", d: f"destination_{level}"})


def cohort_tables(j, max_k=12):
    """Monthly acquisition cohorts on completed journeys. Retention month k = share of the cohort
    with ≥1 completed journey in calendar month (cohort + k). Cells whose month is after
    LAST_FULL_MONTH are left blank (not yet occurred / partial)."""
    c = j[j.completed]
    first = c.groupby("customer_key").month.min().rename("cohort")
    a = c[["customer_key", "month", "service"]].join(first, on="customer_key")
    a["k"] = _mnum(a.month) - _mnum(a.cohort)
    size = first.value_counts().sort_index()
    act = a.drop_duplicates(["customer_key", "k"]).groupby(["cohort", "k"]).size().unstack(fill_value=0)
    ret = act.div(size, axis=0) * 100
    for coh in ret.index:
        for k in ret.columns:
            if coh + k > LAST_FULL_MONTH:
                ret.loc[coh, k] = np.nan
    ret = ret.reindex(columns=range(0, max_k + 1))
    per_cust = c.groupby("customer_key").size()
    summ = pd.DataFrame({"new_customers": size,
                         "active_in_acquisition_month": act.get(0, pd.Series(dtype=int)).reindex(size.index)})
    for k in (1, 2, 3, 6):
        summ[f"m{k}_retention_pct"] = ret[k].round(1) if k in ret else np.nan
    joined = first.to_frame().join(per_cust.rename("n"))
    summ["repeat_customer_pct"] = joined.groupby("cohort").n.apply(lambda x: 100 * (x >= 2).mean()).round(1)
    summ["avg_trips_per_customer"] = joined.groupby("cohort").n.mean().round(2)
    mix = a.groupby("cohort").service.apply(lambda s: 100 * (s == GC).mean())
    summ["green_card_journey_share_pct"] = mix.round(1)
    summ["long_route_journey_share_pct"] = (100 - mix).round(1)
    summ["months_observed"] = [(LAST_FULL_MONTH - coh).n if coh <= LAST_FULL_MONTH else 0 for coh in summ.index]
    summ["maturity"] = np.select(
        [summ.months_observed >= 6, summ.months_observed >= 1, summ.index == LAST_FULL_MONTH],
        ["Mature (≥6 months observed)", "Incomplete (<6 months observed)", "Too new (no follow-up month yet)"],
        "Partial acquisition month")
    summ.index = summ.index.astype(str); ret.index = ret.index.astype(str)
    return summ.reset_index().rename(columns={"index": "cohort_month", "cohort": "cohort_month"}), ret.round(1)


def frequency_table(prof):
    lr_col = LR.lower().replace(" / ", "_").replace("-", "_") + "_only"
    f = prof.groupby("frequency_band", observed=False).agg(
        customers=("journeys", "size"), journeys=("journeys", "sum"),
        **{lr_col: ("services", lambda s: int((s == f"{LR} only").sum()))},
        green_card_only=("services", lambda s: int((s == "Green Card only").sum())),
        both=("services", lambda s: int((s == "Both").sum())))
    f["customer_pct"] = (100 * f.customers / f.customers.sum()).round(1)
    f["journey_pct"] = (100 * f.journeys / f.journeys.sum()).round(1)
    return f.reset_index()


def segment_table(prof):
    s = prof.groupby("segment", observed=False).agg(
        customers=("journeys", "size"), avg_journeys=("journeys", "mean"),
        avg_active_months=("active_months", "mean"), median_last_journey=("last_journey", "median"))
    s["customer_pct"] = (100 * s.customers / s.customers.sum()).round(1)
    s["avg_journeys"] = s.avg_journeys.round(2); s["avg_active_months"] = s.avg_active_months.round(2)
    s["median_last_journey"] = s.median_last_journey.dt.date
    return s.reset_index()


def service_monthly(j):
    c = j[j.completed]
    m = c.groupby(["month", "service"]).agg(journeys=("customer_key", "size"),
                                            customers=("customer_key", "nunique")).reset_index()
    m["month"] = m.month.astype(str)
    return m


def state_frequency_matrix(prof):
    return prof.groupby(["primary_boarding_state", "frequency_band"], observed=False).size().rename("customers").reset_index()
