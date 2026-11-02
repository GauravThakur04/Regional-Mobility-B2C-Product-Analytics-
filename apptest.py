import sys, os; sys.path.insert(0, os.getcwd())
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("app.py", default_timeout=900).run()
ok = lambda: [e.value for e in at.exception] or "ok"
gc = [s for s in at.selectbox if s.label == "Green Card"][0]
gc.set_value("Green Card only").run(); print("GC only:", ok(), [(m.label, m.value) for m in at.metric][:2])
[s for s in at.selectbox if s.label == "Green Card"][0].set_value("All trips").run()
at.multiselect[0].set_value(["Haryana", "Punjab"]).run(); print("HR+PB:", ok(), [(m.label, m.value) for m in at.metric][:4])
