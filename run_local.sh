#!/bin/sh
# Local dashboard (shows phone numbers): served to this computer only.
cd "$(dirname "$0")" && exec ./venv/bin/streamlit run app.py --server.address localhost --server.port 8501 --server.headless true
