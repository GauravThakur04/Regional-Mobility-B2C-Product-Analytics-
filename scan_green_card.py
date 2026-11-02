"""Read-only sweep: which tables contain 'green' / 'card' / Hindi equivalents in their VALUES?
Skips the multi-GB pricing/inventory tables. One bounded query per table (LIMIT), timeouts tolerated."""
import psycopg2
from db import connect

SKIP_OVER_BYTES = 6 * 1024**3
PATTERNS = {
    "green": r"green",
    "card": r"card",
    "ग्रीन/हरा": r"(ग्रीन|हरा)",
    "कार्ड": r"कार्ड",
}

conn = connect()
cur = conn.cursor()
cur.execute("SET statement_timeout = '240s'")
cur.execute("""select c.relname, pg_total_relation_size(c.oid) from pg_class c join pg_namespace n on n.oid=c.relnamespace
               where n.nspname='public' and c.relkind='r' order by 2""")
tables = cur.fetchall()
for name, size in tables:
    if size > SKIP_OVER_BYTES:
        print(f"SKIP  {name} ({size / 1024**3:.0f} GB)", flush=True)
        continue
    hits = {}
    for lab, pat in PATTERNS.items():
        try:
            cur.execute(f'select left(t::text, 400) from "{name}" t where t::text ~* %s limit 3', (pat,))
            rows = cur.fetchall()
            if rows:
                hits[lab] = [r[0] for r in rows]
        except psycopg2.Error as e:
            hits[lab] = [f"<error: {e.pgerror.strip()[:60] if e.pgerror else e}>"]
            conn.rollback() if not conn.autocommit else None
    if hits:
        print(f"HIT   {name}: " + " | ".join(f"{k}: {v[0][:250]}" for k, v in hits.items()), flush=True)
print("DONE", flush=True)
