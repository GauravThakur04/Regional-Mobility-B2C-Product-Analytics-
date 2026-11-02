"""Pull the card-service tables (apnibus-service-db) into data/. Run with DBENV=.dbenv_service."""
import os
os.environ.setdefault("DBENV", ".dbenv_service")
import db
HERE = os.path.dirname(os.path.abspath(__file__))
salt = open(os.path.join(HERE, ".salt")).read().strip()
for name in ("20_card_bookings", "21_ota_stops", "24_card_customers"):
    df = db.q(open(os.path.join(HERE, "sql", name + ".sql")).read(), {"salt": salt})
    df.to_pickle(os.path.join(HERE, "data", name + ".pkl"))
    print(name, df.shape)
