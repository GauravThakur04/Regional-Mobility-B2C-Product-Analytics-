"""Build the data snapshot the online (Streamlit Cloud) app reads when data/ isn't there.
It holds the *finished* tables only — no phone numbers, raw stop names masked/dropped.  Run after refreshing data/:
    ./venv/bin/python make_snapshot.py
"""
import os
import re
import pandas as pd
import metrics as M
import paid as P
import card as CD

OUT = os.path.join(M.HERE, "snapshot")
PHONE = re.compile(r"(?<!\d)[6-9]\d{9}(?!\d)")


def no_phones(df, name):
    for col in df.columns:
        if df[col].dtype == object or str(df[col].dtype).startswith("string"):
            hits = df[col].dropna().astype(str).str.contains(PHONE).sum()
            assert hits == 0, f"{name}.{col}: {hits} values look like phone numbers"


os.makedirs(OUT, exist_ok=True)
_, j = P.build()
j = j.drop(columns=[c for c in j.columns if c.endswith("_raw")] + ["boarding_stop", "drop_stop", "origin_stop", "dest_stop",
                                                                   "stop_route"], errors="ignore")
ct = CD.build()
cu = CD.customers().drop(columns=["phone"], errors="ignore")
for name, df in (("journeys", j), ("card_taps", ct), ("card_customers", cu)):
    no_phones(df, name)
    df.to_parquet(os.path.join(OUT, f"{name}.parquet"), index=False)
    back = pd.read_parquet(os.path.join(OUT, f"{name}.parquet"))
    assert len(back) == len(df) and list(back.columns) == list(df.columns), name
    print(f"{name:15s} {len(df):>7,} rows  {os.path.getsize(os.path.join(OUT, name + '.parquet')) / 1e6:.1f} MB")
