"""Read-only connection helper for the commuter DB."""
import os, sys, warnings
import psycopg2
import pandas as pd

warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")
HERE = os.path.dirname(os.path.abspath(__file__))


def _env():
    env = {}
    with open(os.path.join(HERE, os.environ.get("DBENV", ".dbenv"))) as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                env[k] = v
    return env


def connect():
    e = _env()
    conn = psycopg2.connect(
        host=e["DB_HOST"], port=e["DB_PORT"], dbname=e["DB_NAME"],
        user=e["DB_USER"], password=e["DB_PASS"], sslmode=e["DB_SSLMODE"],
        connect_timeout=20,
        options="-c default_transaction_read_only=on -c statement_timeout=300000",
    )
    conn.set_session(readonly=True, autocommit=True)
    return conn


_conn = None


def q(sql, params=None):
    global _conn
    if _conn is None:
        _conn = connect()
    return pd.read_sql_query(sql, _conn, params=params)


if __name__ == "__main__":
    pd.set_option("display.width", 250, "display.max_columns", 50, "display.max_rows", 500,
                  "display.max_colwidth", 60)
    sql = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    print(q(sql).to_string())
