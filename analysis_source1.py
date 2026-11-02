"""Our buses only (ticket_ticketnew.source = 1): how tickets are booked (App/Web vs Green Card),
who books regularly, monthly cohorts, and region (district) → region travel."""
import os
import numpy as np
import pandas as pd
import metrics as M

OUT = os.path.join(M.HERE, "outputs_source1")
os.makedirs(OUT, exist_ok=True)

t = M.build_tickets("source1")
j = M.build_journeys(t)
prof = M.customer_profile(j)
c = j[j.completed]
app_era = c[c.town_route != M.UNMAPPED_LEGACY]          # 2024+ tickets that carry towns/districts


def rn(df):
    df = df.copy()
    df.columns = [str(x).replace("long_route", "app_web") for x in df.columns]
    return df


# ---------------------------------------------------------------- how tickets were booked
att = t[t.attempt].copy()
att["era"] = np.where(att.meta_from.notna(), "Legacy (Dec-2021 → Apr-2024)", "App era (2024 →)")
att["outcome"] = np.select([att.valid & (att.service == M.GC), att.valid], ["Green Card booking", "App / Web – paid online"],
                           "App / Web – payment not completed")
booked = (att.groupby(["era", "outcome"]).agg(tickets=("ticket_id", "size"), customers=("customer_key", "nunique"),
                                              median_fare=("payable_amount", "median"))
          .reset_index())
by_month = (c.groupby(["month", "service"]).agg(journeys=("customer_key", "size"), customers=("customer_key", "nunique"))
            .reset_index())
by_month["month"] = by_month.month.astype(str)

lr = set(c.customer_key[c.service == M.LR]); gc = set(c.customer_key[c.service == M.GC])
overview = pd.DataFrame([
    ("Customers who travelled on our buses (≥1 completed journey)", len(lr | gc)),
    ("Booked via App / Web (paid online)", len(lr)),
    ("Booked via Green Card", len(gc)),
    ("Used both App/Web and Green Card", len(lr & gc)),
    ("App / Web only", len(lr - gc)),
    ("Green Card only", len(gc - lr)),
    ("Valid tickets", int(t.valid.sum())),
    ("Completed journeys (de-duplicated)", len(c)),
    ("   of which Green Card journeys", int((c.service == M.GC).sum())),
    ("   of which App / Web journeys", int((c.service == M.LR).sum())),
    ("App / Web checkouts never paid (excluded)", int((t.attempt & ~t.valid).sum())),
    ("Repeat customers (≥2 journeys)", int(prof.is_repeat.sum())),
    ("Regular customers (travelled in ≥3 different months)", int(prof.is_regular.sum())),
    ("Frequent customers (≥6 journeys)", int((prof.journeys >= 6).sum())),
    ("Journeys with region (district) known — 2024 onward", len(app_era)),
    ("Customers with region known", app_era.customer_key.nunique()),
    ("First / last journey", f"{c.journey_date.min().date()} → {c.journey_date.max().date()}"),
], columns=["metric", "value"])

summ, ret = M.cohort_tables(j, max_k=24)
# Cohorts restricted to the app era too, since legacy and app-era customers behave differently.
summ_app, ret_app = M.cohort_tables(app_era, max_k=18)

region_matrix = M.state_route_matrix(j, level="region")
region_matrix = region_matrix[region_matrix.origin_region != M.UNMAPPED_LEGACY].sort_values("journeys", ascending=False)

regulars = prof[prof.is_regular | (prof.journeys >= 6)].reset_index()
top_rt = (app_era.groupby(["customer_key", "region_route"]).size().rename("trips").reset_index()
          .sort_values("trips", ascending=False).drop_duplicates("customer_key"))
regulars = regulars.merge(top_rt, on="customer_key", how="left")
reg_by_route = (regulars.dropna(subset=["region_route"]).groupby("region_route")
                .agg(regular_customers=("customer_key", "size"), avg_journeys=("journeys", "mean"),
                     green_card_users=("gc_journeys", lambda s: int((s > 0).sum())),
                     latest=("last_journey", "max"))
                .round(2).reset_index().sort_values("regular_customers", ascending=False))
reg_by_route["latest"] = reg_by_route.latest.dt.date

cust = regulars.rename(columns={"customer_key": "customer_id_anon"})
cust["customer_id_anon"] = "C" + cust.customer_id_anon.str[:12]
for col in ("first_journey", "last_journey"):
    cust[col] = cust[col].dt.date

tables = {
    "01_overview": overview,
    "02_how_booked": booked,
    "03_monthly_by_booking_method": by_month,
    "04_frequency_bands": rn(M.frequency_table(prof)),
    "05_recency_segments": M.segment_table(prof),
    "06_cohort_summary_all": summ,
    "07_cohort_retention_all": ret.reset_index().rename(columns={"cohort": "cohort_month", "index": "cohort_month"}),
    "08_cohort_summary_app_era": summ_app,
    "09_cohort_retention_app_era": ret_app.reset_index().rename(columns={"cohort": "cohort_month", "index": "cohort_month"}),
    "10_region_to_region": region_matrix,
    "11_region_boarding_summary": rn(M.state_table(j, "from", "region")),
    "12_region_destination_summary": rn(M.state_table(j, "to", "region")),
    "13_routes_town": rn(M.route_table(j, "town")),
    "14_regulars_by_region_route": reg_by_route,
    "15_regular_customers_anon": cust[["customer_id_anon", "journeys", "active_months", "first_journey", "last_journey",
                                       "lr_journeys", "gc_journeys", "services", "segment", "region_route", "trips"]]
    .rename(columns={"lr_journeys": "app_web_journeys", "region_route": "most_travelled_region_route",
                     "trips": "trips_on_that_route"}),
}
with pd.ExcelWriter(os.path.join(OUT, "our_buses_source1_analysis.xlsx")) as xw:
    for name, df in tables.items():
        df.to_csv(os.path.join(OUT, f"{name}.csv"), index=False)
        df.to_excel(xw, sheet_name=name[:31], index=False)

keep = ["customer_key", "journey_date", "month", "completed", "service", "channel", "from_state", "to_state",
        "from_region", "to_region", "region_route", "from_town", "to_town", "origin_stop", "dest_stop", "town_route",
        "stop_route", "state_route", "tickets_in_journey", "boarding_stop_raw", "drop_stop_raw"]
jj = j[keep].copy()
jj["customer_key"] = "C" + jj.customer_key.str[:12]
jj.to_pickle(os.path.join(M.DATA, "journeys_dashboard_source1.pkl"))

pd.set_option("display.width", 250, "display.max_columns", 30, "display.max_colwidth", 60)
print(overview.to_string(index=False))
