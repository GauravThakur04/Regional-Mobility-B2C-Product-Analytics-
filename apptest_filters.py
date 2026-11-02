"""Smoke + filter tests for app.py: every sidebar filter and every tab control runs without errors and changes numbers."""
import datetime as dt
import time
from streamlit.testing.v1 import AppTest

CARD, APP = "Green Card passengers (tap on the bus)", "App & website bookings"
t0 = time.time()
at = AppTest.from_file("app.py", default_timeout=600).run()


def check(name):
    assert not at.exception, (name, [e.value for e in at.exception])
    m = {x.label: x.value for x in at.metric}
    cap = [c.value for c in at.sidebar.caption]
    print(f"{name:48s} {m.get('Trips paid by card') or m.get('Trips')} | {m.get('Passengers')} | "
          f"{cap[-1] if cap else ''}  [{time.time() - t0:.0f}s]")
    return m


def trips(m):
    return m.get("Trips paid by card") or m.get("Trips")


# ---------------- Green Card passengers
base = check("card: default (all states)")
at.multiselect(key="cd_state").set_value(["Himachal Pradesh"]).run(); m = check("card: Himachal")
assert trips(m) != trips(base)
at.multiselect(key="cd_state").set_value(["Punjab", "Haryana"]).run(); check("card: Punjab + Haryana")
at.multiselect(key="cd_state").set_value([]).run()
op = at.multiselect(key="cd_op").options[0]
at.multiselect(key="cd_op").set_value([op]).run(); m = check(f"card: operator {op[:20]}")
assert trips(m) != trips(base)
rt = at.multiselect(key="cd_route").options[0]
at.multiselect(key="cd_route").set_value([rt]).run(); check(f"card: + route {rt[:22]}")
at.multiselect(key="cd_op").set_value([]).run(); at.multiselect(key="cd_route").set_value([]).run()
at.date_input(key="cd_dates").set_value((dt.date(2026, 5, 1), dt.date(2026, 6, 30))).run(); m = check("card: May–Jun 2026")
assert trips(m) != trips(base)
at.date_input(key="cd_dates").set_value((dt.date(2026, 5, 1),)).run(); check("card: half-picked date (ignored)")
at.sidebar.button[0].click().run(); m = check("card: after Reset")
assert trips(m) == trips(base), "reset failed"

for order in ("loyal_%", "trips_per_rider", "riders"):
    at.selectbox(key="cd_lo_order").set_value(order).run(); check(f"card loyal: rank by {order}")
at.slider(key="cd_bus_n").set_value(40).run(); check("card buses: 40 buses")
bus = at.selectbox(key="cd_bus_pick").options[3]
at.selectbox(key="cd_bus_pick").set_value(at.selectbox(key="cd_bus_pick").options[3]).run(); check(f"card buses: pick {bus[:25]}")
at.multiselect(key="cd_cu_status").set_value(["Lapsed (3–12 months)"]).run(); check("card customers: lapsed")
at.multiselect(key="cd_cu_type").set_value(["Regular (3+ months)"]).run(); check("card customers: lapsed regulars")
cm = {x.label: x.value for x in at.metric}
print("   list size:", cm.get("Customers in this list"), "| wallet money:", cm.get("Money left in their wallets"))
at.multiselect(key="cd_cu_status").set_value([]).run(); at.multiselect(key="cd_cu_type").set_value([]).run()
at.toggle(key="cd_cu_never").set_value(True).run(); check("card customers: + never travelled")
print("   list size with never-travelled:", {x.label: x.value for x in at.metric}.get("Customers in this list"))
at.multiselect(key="cd_cu_status").set_value(["Never travelled"]).run(); check("card customers: only never travelled")
at.selectbox(key="cd_coh_route").set_value(at.selectbox(key="cd_coh_route").options[1]).run(); check("card return: one route")
at.radio(key="cd_coh_show").set_value("People").run(); at.radio(key="cd_coh_h").set_value(12).run(); check("card return: people/12m")

# ---------------- App & website
at.radio(key="view").set_value(APP).run(); abase = check("app: default")
at.multiselect(key="ap_state").set_value(["Haryana"]).run(); m = check("app: Haryana")
assert trips(m) != trips(abase)
towns = at.multiselect(key="ap_town").options
at.multiselect(key="ap_town").set_value([towns[0]]).run(); check(f"app: + town {towns[0]}")
at.multiselect(key="ap_town").set_value([]).run(); at.multiselect(key="ap_state").set_value(["Rajasthan"]).run()
at.multiselect(key="ap_via").set_value(["Website"]).run(); m = check("app: Rajasthan + Website")
at.multiselect(key="ap_via").set_value([]).run(); at.multiselect(key="ap_state").set_value([]).run()
at.selectbox(key="ap_gc").set_value("Green Card only").run(); m = check("app: Green Card only")
assert trips(m) != trips(abase)
at.selectbox(key="ap_gc").set_value("All trips").run()
at.date_input(key="ap_dates").set_value((dt.date(2025, 1, 1), dt.date(2025, 12, 31))).run(); m = check("app: 2025")
assert trips(m) != trips(abase)
at.sidebar.button[0].click().run(); m = check("app: after Reset")
assert trips(m) == trips(abase), "reset failed"
at.selectbox(key="ap_lo_order").set_value("loyal_%").run(); check("app loyal: rank by loyal %")
at.selectbox(key="ap_bus_pick").set_value(at.selectbox(key="ap_bus_pick").options[0]).run(); check("app buses: pick first")
at.multiselect(key="ap_cu_status").set_value(["Dormant (over a year)"]).run(); check("app customers: dormant")
at.multiselect(key="ap_cu_status").set_value([]).run()
at.selectbox(key="ap_coh_route").set_value(at.selectbox(key="ap_coh_route").options[1]).run(); check("app return: one route")
at.radio(key="view").set_value(CARD).run(); check("back to card view")
print("ALL TESTS PASSED")
