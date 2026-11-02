"""Card taps on the conductor machine (apnibus-service-db: service_app_servicebooking).
Route names come from ota_service (first → last town of the bus route); the tap's own boarding/drop stop ids
belong to the POS backend and cannot be resolved here."""
import os
import pandas as pd
import metrics as M

NO_ROUTE = "Route not in OTA data"
BUS_STATES = {"HP": "Himachal Pradesh", "RJ": "Rajasthan", "PB": "Punjab", "BR": "Bihar", "HR": "Haryana",
              "JH": "Jharkhand", "CG": "Chhattisgarh", "UP": "Uttar Pradesh", "DL": "Delhi", "GJ": "Gujarat"}


def build():
    b = pd.read_pickle(os.path.join(M.DATA, "20_card_bookings.pkl"))
    s = pd.read_pickle(os.path.join(M.DATA, "21_ota_stops.pkl"))
    b = b[~b.is_deleted & ~b.is_test_user].copy()

    s = s[~s.svc_deleted & ~s.stop_deleted].copy()
    s["town"] = s.alias_en.where(s.alias_en.str.strip().astype(bool), s.town_alias).str.strip().str.title()
    s = s[s.town.fillna("").astype(bool)]                    # stops with a blank name can't name a route
    ends = s.sort_values("order_index").groupby(["route_id", "service_id"]).town.agg(["first", "last"])
    ends["name"] = ends["first"] + " → " + ends["last"]
    route_name = ends.groupby("route_id").name.agg(lambda x: x.mode()[0])
    operator = s.groupby("route_id").operator_name.agg(lambda x: x.mode()[0])

    b["date"] = pd.to_datetime(b.tapped_at.fillna(b.created_at)).dt.normalize()
    b["month"] = b.date.dt.to_period("M")
    b["route"] = b.busroute_id.map(route_name).fillna(NO_ROUTE)
    b["operator"] = b.busroute_id.map(operator).fillna("Unknown")
    plate = b.bus_number.fillna("").str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)
    b["bus_state"] = plate.str[:2].map(BUS_STATES).fillna("Other / unknown")
    b["bus"] = plate.replace("", "Unknown")
    return b


def customers():
    """Registered card users (incl. never tapped): language, wallet balance, sign-up. Keyed by the hashed mobile."""
    return pd.read_pickle(os.path.join(M.DATA, "24_card_customers.pkl"))
