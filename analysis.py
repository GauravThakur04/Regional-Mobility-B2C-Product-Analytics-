"""All B2C bookings: build every summary table, data-quality check and export from the cached extracts."""
import json, os
import pandas as pd
import metrics as M

OUT = os.path.join(M.HERE, "outputs")
os.makedirs(OUT, exist_ok=True)

t = M.build_tickets("all")
j = M.build_journeys(t)
passes = pd.read_pickle(os.path.join(M.DATA, "02_passes.pkl"))
reg_path = os.path.join(M.DATA, "registered.json")
if not os.path.exists(reg_path):
    from db import q
    n = int(q("select count(distinct contact) n from user_user "
              "where not coalesce(is_test_user,false) and not is_deleted and contact is not null").n[0])
    json.dump({"registered": n}, open(reg_path, "w"))
registered = json.load(open(reg_path))["registered"]

prof = M.customer_profile(j)

tables = {
    "01_overview": M.overview(t, j, passes, registered),
    "02_state_boarding": M.state_table(j, "from"),
    "03_state_destination": M.state_table(j, "to"),
    "04_state_route_matrix": M.state_route_matrix(j),
    "05_routes_town": M.route_table(j, "town"),
    "06_routes_stop": M.route_table(j, "stop", min_customers=5),
    "07_cohort_summary": None, "08_cohort_retention_matrix": None,
    "09_frequency_bands": M.frequency_table(prof),
    "10_recency_segments": M.segment_table(prof),
    "11_service_monthly": M.service_monthly(j),
    "12_state_frequency_matrix": M.state_frequency_matrix(prof),
}
summ, ret = M.cohort_tables(j, max_k=24)
tables["07_cohort_summary"] = summ
tables["08_cohort_retention_matrix"] = ret.reset_index().rename(columns={"index": "cohort_month", "cohort": "cohort_month"})

# Anonymised customer list for targeting (no phone/email; customer_key is a salted hash).
cust = prof.reset_index().rename(columns={"customer_key": "customer_id_anon"})
cust["customer_id_anon"] = "C" + cust.customer_id_anon.str[:12]
top_route = (j[j.completed & (j.town_route != M.UNMAPPED_LEGACY)].groupby(["customer_key", "town_route"]).size()
             .rename("n").reset_index().sort_values("n", ascending=False).drop_duplicates("customer_key"))
top_route["customer_id_anon"] = "C" + top_route.customer_key.str[:12]
cust = cust.merge(top_route[["customer_id_anon", "town_route", "n"]].rename(
    columns={"town_route": "most_travelled_route", "n": "trips_on_that_route"}), on="customer_id_anon", how="left")
for col in ("first_journey", "last_journey"):
    cust[col] = cust[col].dt.date
tables["13_customer_segments_anon"] = cust

# Cross-sell: services split for long-route customers active during the Green Card window.
gc_window = j[j.completed & (j.service == M.GC)].journey_date
w0, w1 = gc_window.min(), gc_window.max()
win = j[j.completed & j.journey_date.between(w0, w1)]
wl = set(win.customer_key[win.service == M.LR]); wg = set(win.customer_key[win.service == M.GC])
tables["14_green_card_window_overlap"] = pd.DataFrame([
    ("Green Card usage window", f"{w0.date()} to {w1.date()}"),
    ("Customers travelling in window", len(wl | wg)),
    ("Long-route customers in window", len(wl)),
    ("Green Card customers in window", len(wg)),
    ("Both in window", len(wl & wg)),
    ("Long-route customers in window who never used Green Card", len(wl - wg)),
    ("Share of window long-route customers who also used Green Card (%)", round(100 * len(wl & wg) / max(len(wl), 1), 1)),
], columns=["metric", "value"])

ch = j[j.completed].groupby("channel").agg(journeys=("customer_key", "size"), customers=("customer_key", "nunique"),
                                           green_card_journeys=("service", lambda s: int((s == M.GC).sum())))
tables["15_channel_breakdown"] = ch.reset_index().sort_values("journeys", ascending=False)

# ---------------------------------------------------------------- data quality
v = t[t.valid]
dq = [
    ("Tickets in ticket_ticketnew", len(t)),
    ("Valid tickets (status=1 AND is_paid, not deleted, not test ticket/user, journey date present)", len(v)),
    ("Excluded: status=1 but unpaid (abandoned checkout; RSRTC/Bitla confirm_booking_status=3)", int((t.attempt & ~t.valid).sum())),
    ("Excluded: cancelled (status=3)", int((t.status == 3).sum())),
    ("Excluded: status NULL (never confirmed)", int(t.status.isna().sum())),
    ("Excluded: other statuses (2, 4)", int(t.status.isin([2, 4]).sum())),
    ("Excluded: soft-deleted", int((t.is_deleted & (t.status == 1)).sum())),
    ("Excluded: test users / test tickets", int(((t.is_test_user | t.is_test_ticket) & (t.status == 1) & ~t.is_deleted).sum())),
    ("Valid tickets with refund_status 1/2 (kept; partial refunds possible)", int(v.refund_status.isin([1, 2]).sum())),
    ("Valid tickets with cancelled_on set (kept; status still confirmed)", int(v.has_cancelled_on.sum())),
    ("Valid tickets that are reschedules (kept as the live ticket)", int(v.is_rescheduled.sum())),
    ("Valid tickets with no user at all (each kept as its own customer)", int(v.no_user.sum())),
    ("Valid tickets with no town ids (legacy 'old prod' migration, 2021-12 → 2024-05)", int((v.from_town_id.isna() | v.to_town_id.isna()).sum())),
    ("Valid tickets with town but no boarding-stop name", int((v.from_town_id.notna() & v.boarding_stop_raw.isna()).sum())),
    ("Valid tickets with town but no drop-stop name", int((v.to_town_id.notna() & v.drop_stop_raw.isna()).sum())),
    ("Valid tickets: boarding state filled from district lookup", int((v.from_state_raw.isna() & (v.from_state != M.UNMAPPED) & (v.from_state != M.UNMAPPED_LEGACY)).sum())),
    ("Valid tickets: boarding state still unmapped (town known)", int((v.from_state == M.UNMAPPED).sum())),
    ("Valid tickets: destination state still unmapped (town known)", int((v.to_state == M.UNMAPPED).sum())),
    ("Valid tickets: journey date earlier than booking date", int((v.journey_date < v.booking_date).sum())),
    ("Valid tickets collapsed as duplicate journeys (same customer/date/route/service)", len(v) - len(j)),
    ("Valid tickets sharing a non-null PNR with another valid ticket (legacy placeholder '000000')", int(v.pnr.dropna().duplicated(keep=False).sum())),
    ("Valid tickets with NULL PNR", int(v.pnr.isna().sum())),
    ("Distinct user ids on valid tickets", v.user_id.nunique()),
    ("Distinct customers after phone de-duplication", v.customer_key.nunique()),
    ("Green Card tickets (ticket_with_pass) with a pass_reward_id", int(v[v.service == M.GC].has_pass_reward.sum())),
    ("Green Card tickets without pass_reward_id", int((~v[v.service == M.GC].has_pass_reward).sum())),
    ("Passenger seats on valid tickets (where seat list present)", int(v.seats.fillna(0).sum())),
    ("Valid tickets with seat list missing", int(v.seats.isna().sum())),
    ("Customer residence (user_user.city) populated", "73 of 109,912 ticket-holders — residence not usable"),
    ("Journey date range (valid)", f"{v.journey_date.min().date()} to {v.journey_date.max().date()}"),
    ("As-of date (completed = journey before this date)", str(M.AS_OF.date())),
]
tables["16_data_quality"] = pd.DataFrame(dq, columns=["check", "value"])

with pd.ExcelWriter(os.path.join(OUT, "commuter_cohort_analysis.xlsx")) as xw:
    for name, df in tables.items():
        df.to_csv(os.path.join(OUT, f"{name}.csv"), index=False)
        df.to_excel(xw, sheet_name=name[:31], index=False)

# Dashboard dataset: journey-level, no PII.
keep = ["customer_key", "journey_date", "month", "completed", "service", "channel", "from_state", "to_state",
        "from_region", "to_region", "region_route", "from_town", "to_town", "origin_stop", "dest_stop", "town_route",
        "stop_route", "state_route", "tickets_in_journey", "boarding_stop_raw", "drop_stop_raw"]
jj = j[keep].copy()
jj["customer_key"] = "C" + jj.customer_key.str[:12]
jj.to_pickle(os.path.join(M.DATA, "journeys_dashboard.pkl"))
json.dump({"registered": registered, "passes_paid": int((passes.is_paid & ~passes.is_deleted & ~passes.is_test_user).sum()),
           "pass_holders": int(passes[passes.is_paid & ~passes.is_deleted & ~passes.is_test_user].customer_key.nunique()),
           "valid_tickets": len(v)}, open(os.path.join(M.DATA, "dashboard_meta.json"), "w"))

pd.set_option("display.width", 250, "display.max_columns", 30, "display.max_colwidth", 60)
print(tables["01_overview"].to_string(index=False))
