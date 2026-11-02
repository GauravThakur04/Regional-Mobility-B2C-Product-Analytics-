"""Pull the ticket, pass and state-lookup datasets once (read-only) and cache them locally."""
import os, secrets, time
from db import q, HERE

DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)

salt_path = os.path.join(HERE, ".salt")
if not os.path.exists(salt_path):
    with open(salt_path, "w") as f:
        f.write(secrets.token_hex(16))
salt = open(salt_path).read().strip()

for name in ["01_tickets", "02_passes", "03_state_lookup"]:
    t0 = time.time()
    sql = open(os.path.join(HERE, "sql", name + ".sql")).read()
    df = q(sql, {"salt": salt})
    df.to_pickle(os.path.join(DATA, name + ".pkl"))
    print(f"{name}: {len(df):,} rows in {time.time() - t0:.0f}s")
