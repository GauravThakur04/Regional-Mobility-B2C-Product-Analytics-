# Regional Mobility — B2C Product Analytics

A Streamlit dashboard showing how passengers use Apnibus buses:
- who travels
- on which routes and buses
- who keeps coming back
- which passengers have lapsed and could be won back

It is built for the team planning state-specific booking apps.

## Two passenger groups

The sidebar switches between two groups. Each comes from its own read-only PostgreSQL database.

| View | Source | What a row is |
|---|---|---|
| **Green Card passengers** | Card-service DB, `service_app_servicebooking` | One tap of the prepaid Green Card on the conductor's ticket machine. |
| **App & website bookings** | Commuter DB, `ticket_ticketnew` where `source = 1` and `is_paid = true` | One paid online booking on our own buses. |

## Tabs in each view

- **Overview:** passengers, trips, state comparison and how people booked.
- **Where people travel** (app & website only): the busiest town-to-town routes and a from/to town grid.
- **Loyal routes:** routes where the same passenger travelled 3 or more times.
- **Buses & their riders:** customers and regular customers for each bus number, with a drill-down into one bus.
- **Customer list:** one row per passenger, showing status (active, slipping, lapsed or dormant), rider type, usual route and last trip. For card passengers it also shows wallet balance and language. The list can be filtered and downloaded.
- **Return rate:** monthly cohorts, showing what share of each month's new passengers travelled again later.

## Privacy

- **Passenger IDs:** every passenger is keyed by a salted hash of their phone number, shown as `C…` IDs.
- **Phone numbers stay on the analyst's computer.** The local dashboard shows them in the Customer list, reading them from the git-ignored `data/` folder, and it only serves to `localhost`. They are never committed and never included in the online snapshot.
- **Read-only access:** the databases are opened read-only (`default_transaction_read_only=on`).
- **Kept out of git:** credentials (`.dbenv*`), the hashing salt (`.salt`), extracted data (`data/`) and exports.

## Online version (Streamlit Cloud)

The app runs from `snapshot/` when `data/` isn't there. `snapshot/` holds three Parquet files of finished tables: no phone numbers, and no raw stop names.

To refresh it:
1. Re-extract `data/`.
2. Run `./venv/bin/python make_snapshot.py`. It refuses to write a file if any value looks like a phone number.
3. Commit and push.

Keep this repo **private**, and keep the Streamlit app's sharing set to specific people.

## Setup

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
cp .dbenv.example .dbenv            # commuter DB credentials
cp .dbenv.example .dbenv_service    # card-service DB credentials
python3 -c "import secrets; print(secrets.token_hex(16))" > .salt
mkdir -p data
./venv/bin/python extract.py                                     # commuter DB → data/
DBENV=.dbenv_service ./venv/bin/python extract_service.py        # card-service DB → data/
./venv/bin/streamlit run app.py
```

`extract.py` pulls the base commuter tables (`sql/01–03`). The dashboard also reads these extracts:
- `05_our_buses_detail.pkl`
- `06_our_buses_paid.pkl`
- `20/21/24_*.pkl`

Each is produced from the matching file in `sql/`, using `db.q(sql, {"salt": salt})`.

## Files

| File | Purpose |
|---|---|
| `app.py` | The dashboard. |
| `paid.py` | Builds app & website trips: validity, towns, routes, booking channel, Green Card pass, bus. |
| `card.py` | Builds Green Card taps: route names from `ota_service`, state from the bus plate. |
| `metrics.py` | Shared definitions: journeys, cohorts, route and state tables. |
| `db.py` | Read-only connection helper (`DBENV` selects the credentials file). |
| `sql/` | Every query used, with comments. |
| `extract.py`, `extract_service.py` | Pull query results into `data/`. |
| `make_snapshot.py` | Builds `snapshot/` for the online app (no phone numbers). |
| `apptest_filters.py` | End-to-end test of every filter and control (Streamlit AppTest). |
| `DATA_DICTIONARY.md` | Field definitions. |
| `analysis*.py`, `app_all_b2c.py`, `app_our_buses_full.py`, `our_buses.py` | Earlier analysis scripts and dashboard versions. |

## Known limits

- **Card trip routes:** each route is the bus's whole route (first → last town). The stop where a passenger actually got on or off is stored in the conductor-machine (POS) system, not in these databases.
- **App & website bus numbers:** recorded only for recent bookings.
- **Booking channel:** recorded reliably only from 2024. Older migrated tickets all show "App".
