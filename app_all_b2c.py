"""Commuter cohort & route dashboard.  Run:  streamlit run app.py
Reads the anonymised journey-level extracts (no phone numbers / emails) and recomputes every
table through metrics.py, so filtered numbers use exactly the exported definitions."""
import json, os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import metrics as M

st.set_page_config(page_title="Commuter Cohorts & Routes", layout="wide")

SCOPE = st.sidebar.radio("Dataset", list(M.SCOPES), format_func=lambda s: M.SCOPES[s]["title"])
M.set_scope(SCOPE)
FOCUS = ["Punjab", "Haryana", "Himachal Pradesh"]
ABBR = {"Punjab": "PB", "Haryana": "HR", "Himachal Pradesh": "HP"}
FOCUS_ON = st.sidebar.checkbox("Focus: Punjab, Haryana & Himachal only", value=True,
                               help="Keeps only trips that start or end in one of these three states.")
st.sidebar.caption("**Our buses** = ticket_ticketnew.source = 1, booked via App/Web (paid online) or Green Card. "
                   "**All B2C** = every channel (RSRTC, private operators, our buses, booth agents).")

BLUE, ORANGE = "#2a78d6", "#eb6834"                      # categorical slots 1 & 2
SVC_COLORS = {M.LR: BLUE, M.GC: ORANGE}
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]  # one-hue blue ramp
FONT = dict(family="Inter, system-ui, sans-serif", size=13, color="#0b0b0b")


def style(fig, h=420):
    fig.update_layout(template="plotly_white", height=h, font=FONT, margin=dict(l=10, r=10, t=40, b=10),
                      hoverlabel=dict(bgcolor="white", font_size=12), legend=dict(orientation="h", y=1.08, x=0),
                      bargap=0.25)
    fig.update_xaxes(gridcolor="#ecebe8", zeroline=False, linecolor="#c3c2b7")
    fig.update_yaxes(gridcolor="#ecebe8", zeroline=False, linecolor="#c3c2b7")
    fig.update_traces(marker_line_width=0, selector=dict(type="bar"))
    return fig


def download(df, name, label="Download CSV"):
    st.download_button(label, df.to_csv(index=False).encode(), f"{name}.csv", "text/csv", key=f"dl_{name}")


@st.cache_data
def load(scope):
    name = "journeys_dashboard.pkl" if scope == "all" else f"journeys_dashboard_{scope}.pkl"
    j = pd.read_pickle(os.path.join(M.DATA, name))
    meta = json.load(open(os.path.join(M.DATA, "dashboard_meta.json")))
    return j, meta


@st.cache_data
def compute(j, scope):
    M.set_scope(scope)
    prof = M.customer_profile(j)
    summ, ret = M.cohort_tables(j, max_k=12)
    return dict(prof=prof, states=M.state_table(j, "from"), dest_states=M.state_table(j, "to"),
                matrix=M.state_route_matrix(j), region_matrix=M.state_route_matrix(j, "region"),
                routes=M.route_table(j, "town"),
                stops=M.route_table(j, "stop", min_customers=3), cohort=summ, ret=ret,
                freq=M.frequency_table(prof), seg=M.segment_table(prof), monthly=M.service_monthly(j))


@st.cache_data
def cohort_for(j, scope):
    M.set_scope(scope)
    return M.cohort_tables(j, max_k=12)


@st.cache_data
def matrix_for(j, scope, level):
    M.set_scope(scope)
    return M.state_route_matrix(j, level)


def state_options(df):
    if FOCUS_ON:
        c = df[df.completed]
        return [s for s in FOCUS if ((c.from_state == s) | (c.to_state == s)).any()]
    s = df[df.completed & ~df.from_state.isin([M.UNMAPPED, M.UNMAPPED_LEGACY])].from_state.value_counts()
    return s.index.tolist()


def touches(df, states):
    """Trips that start or end in any of `states`."""
    return df[df.from_state.isin(states) | df.to_state.isin(states)]


J, META = load(SCOPE)
if FOCUS_ON:
    J = touches(J, FOCUS)

# ---------------------------------------------------------------- filters (one row)
st.title(f"{M.SCOPES[SCOPE]['title']} — cohorts, regions & routes")
if SCOPE == "all":
    st.caption(f"Source: ab_commuter (read-only). Valid booking = confirmed **and paid** ticket; journeys are de-duplicated "
               f"per customer/date/route/service. Completed = journey date before {M.AS_OF.date()}. "
               f"Green Card = coupon_userpass pass applied to the ticket (ticket_with_pass). Long-route = every other valid ticket.")
else:
    st.caption(f"Source: ab_commuter (read-only), ticket_ticketnew.source = 1. Two ways to book: **App / Web** (counted "
               f"when paid online) or **Green Card** (the card is the payment, so counted without online payment). "
               f"Completed = journey date before {M.AS_OF.date()}. Tickets before May-2024 have no route data "
               f"(shown as 'Unmapped (legacy ticket)').")
if FOCUS_ON:
    cj = J[J.completed]
    per = {s: touches(cj, [s]).customer_key.nunique() for s in FOCUS}
    st.warning(f"**Focus: Punjab, Haryana & Himachal** — trips that start or end in these states only: "
               f"**{cj.customer_key.nunique():,} people, {len(cj):,} trips** "
               f"({', '.join(f'{s} {n:,}' for s, n in per.items())} people). This is a small sample, so treat "
               f"percentages on small groups with care. Untick the box in the sidebar to see everything.")
f1, f2, f3, f4 = st.columns([2, 2, 1.3, 2.5])
dmin, dmax = J.journey_date.min().date(), J.journey_date.max().date()
dr = f1.date_input("Journey date range", (dmin, dmax), min_value=dmin, max_value=dmax)
states = sorted(J.from_state.unique(), key=lambda s: (-(J.from_state == s).sum()))
sel_states = f2.multiselect("Boarding state", states, placeholder="All states")
sel_svc = f3.multiselect("Service", [M.LR, M.GC], placeholder="Both")
top_routes = J.town_route[J.town_route != M.UNMAPPED_LEGACY].value_counts().index[:3000].tolist()
sel_routes = f4.multiselect("Route (town → town)", top_routes, placeholder="All routes")

f = J
if isinstance(dr, (tuple, list)) and len(dr) == 2:
    f = f[(f.journey_date >= pd.Timestamp(dr[0])) & (f.journey_date <= pd.Timestamp(dr[1]))]
if sel_states:
    f = f[f.from_state.isin(sel_states)]
if sel_svc:
    f = f[f.service.isin(sel_svc)]
if sel_routes:
    f = f[f.town_route.isin(sel_routes)]
if f[f.completed].empty:
    st.warning("No completed journeys match these filters.")
    st.stop()
filtered = len(f) != len(J)
R = compute(f, SCOPE)
prof = R["prof"]

tabs = st.tabs(["Executive summary", "States", "Retention cohorts", "Route heatmap", "Popular routes",
                "Service comparison", "Customer frequency", "Recent activity", "Definitions"])

# ---------------------------------------------------------------- 1. executive summary
with tabs[0]:
    c = f[f.completed]
    lr = set(c.customer_key[c.service == M.LR]); gc = set(c.customer_key[c.service == M.GC])
    k = st.columns(4)
    k[0].metric("Unique customers (completed journeys)", f"{len(lr | gc):,}")
    k[1].metric("Completed journeys", f"{len(c):,}")
    k[2].metric("Repeat customers (2+ journeys)", f"{int(prof.is_repeat.sum()):,}",
                f"{100 * prof.is_repeat.mean():.1f}% of customers", delta_color="off")
    k[3].metric("Regular customers (3+ active months)", f"{int(prof.is_regular.sum()):,}",
                f"{100 * prof.is_regular.mean():.1f}% of customers", delta_color="off")
    k = st.columns(4)
    k[0].metric(f"{M.LR} customers", f"{len(lr):,}")
    k[1].metric("Green Card customers", f"{len(gc):,}")
    k[2].metric("Used both services", f"{len(lr & gc):,}")
    k[3].metric("Valid tickets (incl. upcoming)", f"{int(f.tickets_in_journey.sum()):,}")
    if not filtered and SCOPE == "all":
        st.caption(f"Database-wide: {META['registered']:,} registered customers (distinct phone); "
                   f"{META['pass_holders']:,} bought a Green Card; {META['valid_tickets']:,} valid tickets.")

    a, b = st.columns([1, 1.4])
    ov = pd.DataFrame({"group": [f"{M.LR} only", "Both", "Green Card only"],
                       "customers": [len(lr - gc), len(lr & gc), len(gc - lr)]})
    fig = px.bar(ov, x="customers", y="group", orientation="h", text="customers",
                 color="group", color_discrete_map={f"{M.LR} only": BLUE, "Both": "#52514e", "Green Card only": ORANGE})
    fig.update_traces(texttemplate="%{text:,}", textposition="outside", hovertemplate="%{y}: %{x:,} customers<extra></extra>")
    a.plotly_chart(style(fig, 260).update_layout(showlegend=False, title="Service overlap (customers)",
                                                 yaxis_title=None, xaxis_title=None), width="stretch")
    m = c.groupby("month").agg(journeys=("customer_key", "size"), customers=("customer_key", "nunique")).reset_index()
    m["month"] = m.month.dt.to_timestamp()
    fig = px.line(m, x="month", y="customers", markers=False)
    fig.update_traces(line=dict(color=BLUE, width=2), hovertemplate="%{x|%b %Y}: %{y:,} active customers<extra></extra>")
    b.plotly_chart(style(fig, 260).update_layout(title="Active customers per month", yaxis_title=None, xaxis_title=None,
                                                 hovermode="x unified"), width="stretch")
    ov_tbl = pd.DataFrame([("Unique customers", len(lr | gc)), (f"{M.LR} customers", len(lr)),
                           ("Green Card customers", len(gc)), ("Both", len(lr & gc)),
                           (f"{M.LR} only", len(lr - gc)), ("Green Card only", len(gc - lr)),
                           ("Completed journeys", len(c)), ("Repeat customers", int(prof.is_repeat.sum())),
                           ("Regular customers", int(prof.is_regular.sum()))], columns=["metric", "value"])
    download(ov_tbl, "executive_summary")

# ---------------------------------------------------------------- 2. states
with tabs[1]:
    s = R["states"]
    st.subheader("Boarding-state summary")
    st.caption("State = where the customer boarded (from the stop's town). Customer residence is not recorded "
               "(user city is filled for 73 of ~110k travellers). A customer who boards in two states is counted in both. "
               "'Unmapped (legacy ticket)' = pre-May-2024 migrated tickets with no stop data.")
    show = s[s.boarding_state != M.UNMAPPED_LEGACY]
    top = show.head(15)
    hm = R["prof"].reset_index()
    hm = hm[hm.primary_boarding_state.isin(top.boarding_state)]
    mat = hm.groupby(["primary_boarding_state", "frequency_band"], observed=False).size().unstack(fill_value=0)
    mat = mat.reindex(top.boarding_state).dropna(how="all")
    if len(mat):
        pct = mat.div(mat.sum(axis=1), axis=0) * 100
        fig = go.Figure(go.Heatmap(z=pct.values, x=[str(x) for x in pct.columns], y=pct.index, colorscale=SEQ,
                                   customdata=mat.values, text=[[f"{v:.0f}%" for v in r] for r in pct.values],
                                   texttemplate="%{text}", colorbar=dict(title="% of state"),
                                   hovertemplate="%{y} · %{x}<br>%{customdata:,} customers (%{z:.1f}%)<extra></extra>"))
        st.plotly_chart(style(fig, 520).update_layout(title="Customers by usage band, top-15 boarding states "
                                                      "(% of the state's customers; primary boarding state)",
                                                      yaxis=dict(autorange="reversed")), width="stretch")
    a, b = st.columns(2)
    fig = px.bar(top.sort_values("unique_customers"), x="unique_customers", y="boarding_state", orientation="h",
                 text="unique_customers")
    fig.update_traces(marker_color=BLUE, texttemplate="%{text:,}", textposition="outside",
                      hovertemplate="%{y}: %{x:,} customers<extra></extra>")
    a.plotly_chart(style(fig, 480).update_layout(title="Unique customers by boarding state", xaxis_title=None,
                                                 yaxis_title=None), width="stretch")
    rr = show[show.unique_customers >= 100].sort_values("repeat_customer_pct").tail(15)
    fig = px.bar(rr, x="repeat_customer_pct", y="boarding_state", orientation="h", text="repeat_customer_pct",
                 custom_data=["unique_customers"])
    fig.update_traces(marker_color=BLUE, texttemplate="%{text:.1f}%", textposition="outside",
                      hovertemplate="%{y}: %{x:.1f}% repeat · %{customdata[0]:,} customers<extra></extra>")
    b.plotly_chart(style(fig, 480).update_layout(title="Repeat-customer % (states with ≥100 customers)",
                                                 xaxis_title=None, yaxis_title=None), width="stretch")
    st.dataframe(s, width="stretch", hide_index=True)
    download(s, "state_boarding_summary")
    with st.expander("Destination-state summary"):
        st.dataframe(R["dest_states"], width="stretch", hide_index=True)
        download(R["dest_states"], "state_destination_summary")

# ---------------------------------------------------------------- 3. cohorts
with tabs[2]:
    st.subheader("Do new customers come back?")
    c1, c2, c3 = st.columns([2, 1.2, 1.2])
    all_lbl = "All three states" if FOCUS_ON else "All states"
    coh_state = c1.selectbox("State (trip starts or ends here)" if FOCUS_ON else "State (where the customer boards)",
                             [all_lbl] + state_options(f), key="coh_state")
    horizon = c2.radio("Look ahead", [6, 12], format_func=lambda x: f"{x} months", horizontal=True, key="coh_h")
    min_n = c3.number_input("Hide groups smaller than", 0, 5000, 10 if FOCUS_ON else 20, step=5, key="coh_min",
                            help="Very small groups give jumpy percentages (1 person out of 3 = 33%).")
    if coh_state == all_lbl:
        fc = f
    else:
        fc = touches(f, [coh_state]) if FOCUS_ON else f[f.from_state == coh_state]
    if fc[fc.completed].empty:
        st.info("No completed journeys for this state with the current filters.")
    else:
        summ, ret = cohort_for(fc, SCOPE)
        size = summ.set_index("cohort_month").new_customers
        ks = [k for k in range(1, horizon + 1) if k in ret.columns]
        keep_rows = size[size >= min_n].index
        r = ret.loc[ret.index.isin(keep_rows), ks]
        if coh_state == all_lbl:
            where = " to/from Punjab, Haryana or Himachal" if FOCUS_ON else ""
        else:
            where = f" to/from {coh_state}" if FOCUS_ON else f" boarding in {coh_state}"

        # Plain-language example from the biggest group that has a 1-month and 3-month result.
        ex = summ[(summ.new_customers >= min_n) & summ.m1_retention_pct.notna() & summ.m3_retention_pct.notna()]
        example = ""
        if len(ex):
            e = ex.sort_values("new_customers").iloc[-1]
            mon = pd.Period(e.cohort_month).strftime("%b %Y")
            example = (f"**Example:** {int(e.new_customers):,} people took their first trip{where} in **{mon}**. "
                       f"**{e.m1_retention_pct:.1f}%** of them travelled again 1 month later, and "
                       f"**{e.m3_retention_pct:.1f}%** travelled 3 months later.")
        st.info("**How to read this.** We group customers by the month of their *first* trip. Then we check what "
                "share of each group travelled again 1, 2, 3… months later. Higher = more loyal.  \n" + example)

        # 1) Simple answer: on average, what share come back after N months?
        sz = size.reindex(r.index)
        avg = [((r[k] * sz)[r[k].notna()].sum() / sz[r[k].notna()].sum()) if r[k].notna().any() else None for k in ks]
        av = pd.DataFrame({"when": [f"After {k} mo" for k in ks], "pct": avg}).dropna()
        fig = px.bar(av, x="when", y="pct", text="pct")
        fig.update_traces(marker_color=BLUE, texttemplate="%{text:.1f}%", textposition="outside",
                          hovertemplate="%{x}: %{y:.1f}% travelled again<extra></extra>")
        st.plotly_chart(style(fig, 300).update_layout(
            title=f"On average, what % of new customers{where} travel again?", xaxis_title=None,
            yaxis_title="% of new customers", yaxis=dict(ticksuffix="%")), width="stretch")

        # 2) Detail: one row per starting month.
        opts = list(r.index)
        if opts:
            default = "2024-03" if "2024-03" in opts else opts[0]
            start = st.select_slider("Show groups starting from", options=opts, value=default, key="coh_start")
            rr = r.loc[start:]
            ylab = [f"{pd.Period(i).strftime('%b %Y')} · {int(size[i]):,} people" for i in rr.index]
            zmax = rr.max().max()
            fig = go.Figure(go.Heatmap(
                z=rr.values, x=[f"After {k} mo" for k in rr.columns], y=ylab, colorscale=SEQ, zmin=0,
                zmax=max(10, float(zmax) if pd.notna(zmax) else 0),
                text=[["" if pd.isna(v) else f"{v:.0f}%" for v in row] for row in rr.values], texttemplate="%{text}",
                colorbar=dict(title="% came back", ticksuffix="%"),
                hovertemplate="First trip: %{y}<br>%{x}: %{z:.1f}% travelled again<extra></extra>"))
            st.plotly_chart(style(fig, max(380, 26 * len(rr) + 120)).update_layout(
                title="Each row = people whose first trip was in that month · darker = more came back",
                yaxis=dict(autorange="reversed")), width="stretch")
            st.caption(f"Empty cells = that month hasn't finished yet (data runs to {M.LAST_FULL_MONTH.strftime('%b %Y')}). "
                       f"Groups under {min_n} people are hidden.")
        friendly = summ.rename(columns={
            "cohort_month": "first_trip_month", "new_customers": "new_people", "m1_retention_pct": "came_back_after_1_mo_%",
            "m2_retention_pct": "after_2_mo_%", "m3_retention_pct": "after_3_mo_%", "m6_retention_pct": "after_6_mo_%",
            "repeat_customer_pct": "ever_travelled_again_%", "avg_trips_per_customer": "avg_trips_per_person",
            "green_card_journey_share_pct": "green_card_trip_share_%"}).drop(
            columns=["active_in_acquisition_month", "long_route_journey_share_pct", "months_observed"])
        with st.expander("Full table"):
            st.dataframe(friendly, width="stretch", hide_index=True)
        download(friendly, f"cohort_summary_{coh_state.replace(' ', '_')}")

# ---------------------------------------------------------------- 4. route heatmap
with tabs[3]:
    st.subheader("Where do customers travel from and to?")
    opts = state_options(f)
    h1, h2 = st.columns([2, 3])
    ALL = "All three states" if FOCUS_ON else "All states (compare states)"
    hm_state = h1.selectbox("State" if FOCUS_ON else "Starting state", [ALL] + opts,
                            index=1 if (SCOPE == "source1" and opts and not FOCUS_ON) else 0, key="hm_state",
                            help="Pick a state to see its districts." if FOCUS_ON else
                                 "Pick a state to see its districts instead of whole states.")
    labels = {"unique_customers": "Number of people", "repeat_customer_pct": "% who travelled it again",
              "regular_customers": f"Regular riders ({M.ROUTE_REGULAR_MIN_TRIPS}+ trips)"}
    metric = h2.radio("Show in each box", list(labels), horizontal=True, format_func=labels.get, key="hm_metric")

    if FOCUS_ON:
        # Districts inside the chosen focus state(s); every other state collapses to its name
        # (e.g. all of Rajasthan = one row/column), so the grid stays readable.
        chosen = FOCUS if hm_state == ALL else [hm_state]
        src = touches(f, chosen).copy()
        for side in ("from", "to"):
            dist = src[f"{side}_region"].str.replace(r" \([^)]*\)$", "", regex=True)
            inside = src[f"{side}_state"].isin(chosen)
            tag = src[f"{side}_state"].map(ABBR) if len(chosen) > 1 else None
            lbl = dist + (" (" + tag + ")" if tag is not None else "")
            src[f"{side}_lbl"] = lbl.where(inside, src[f"{side}_state"])
        level, n_top = "lbl", 15
    elif hm_state == ALL:
        level, n_top, src = "state", 12, f
    else:
        level, n_top, src = "region", 15, f[f.from_state == hm_state]
    mx = matrix_for(src, SCOPE, level)
    oc, dc = f"origin_{level}", f"destination_{level}"
    mx = mx[~mx[oc].isin([M.UNMAPPED, M.UNMAPPED_LEGACY]) & ~mx[dc].isin([M.UNMAPPED, M.UNMAPPED_LEGACY])].copy()
    if level == "region":   # inside one state, "Jaipur (Rajasthan)" → "Jaipur"; other states keep their name
        for col in (oc, dc):
            mx[col] = mx[col].str.replace(f" ({hm_state})", "", regex=False)
    lname = {"state": "state", "region": "district", "lbl": "district / state"}[level]
    if FOCUS_ON:
        st.caption(f"Rows and columns are **districts** of {', '.join(chosen)}; other states are shown as one "
                   "box each (e.g. 'Rajasthan').")

    if mx.empty:
        st.info("No trips with route data for this selection (tickets before May-2024 have no route).")
    else:
        topo = mx.groupby(oc).unique_customers.sum().nlargest(n_top).index
        topd = mx.groupby(dc).unique_customers.sum().nlargest(n_top).index
        sub = mx[mx[oc].isin(topo) & mx[dc].isin(topd)]
        best = mx.sort_values("unique_customers", ascending=False).iloc[0]
        st.info(f"**How to read this.** Each **row** is where people start ({lname}) and each **column** is where they go. "
                f"Darker box = bigger number. Read across a row to see where people from that {lname} travel.  \n"
                f"**Example:** the busiest trip is **{best[oc]} → {best[dc]}**: {int(best.unique_customers):,} people, "
                f"{int(best.journeys):,} trips, {best.repeat_customer_pct:.0f}% travelled it again."
                + ("" if level != "region" else f"  \nA box on the diagonal (e.g. {best[oc]} → {best[oc]}) is a trip "
                   f"between two towns inside the same district."))

        # Simple view first: top 10 trips as a ranked list.
        top10 = mx.sort_values(metric, ascending=False)
        if metric == "repeat_customer_pct":
            top10 = top10[top10.unique_customers >= 30]          # % on tiny routes is noise
        top10 = top10.head(10).assign(trip=lambda d: d[oc] + " → " + d[dc]).iloc[::-1]
        fig = px.bar(top10, x=metric, y="trip", orientation="h", text=metric,
                     custom_data=["unique_customers", "journeys", "repeat_customer_pct", "regular_customers"])
        fig.update_traces(marker_color=BLUE, textposition="outside",
                          texttemplate="%{text:.0f}%" if metric == "repeat_customer_pct" else "%{text:,}",
                          hovertemplate="%{y}<br>%{customdata[0]:,} people · %{customdata[1]:,} trips<br>"
                                        "%{customdata[2]:.0f}% travelled again · %{customdata[3]:,} regulars<extra></extra>")
        title_where = {"state": "between states", "region": f"from {hm_state} districts", "lbl": f"to or from {hm_state.lower() if hm_state == ALL else hm_state}"}[level]
        st.plotly_chart(style(fig, 420).update_layout(
            title=f"Top 10 trips {title_where} — {labels[metric].lower()}"
                  + (" (trips with 30+ people)" if metric == "repeat_customer_pct" else ""),
            xaxis_title=None, yaxis_title=None), width="stretch")

        # Detail: the grid.
        pv = sub.pivot(index=oc, columns=dc, values=metric).reindex(index=topo, columns=topd)
        pc = sub.pivot(index=oc, columns=dc, values="unique_customers").reindex(index=topo, columns=topd)
        z = pv.values
        fig = go.Figure(go.Heatmap(
            z=z, x=pv.columns, y=pv.index, colorscale=SEQ, customdata=pc.values,
            text=[["" if pd.isna(v) else (f"{v:.0f}%" if metric == "repeat_customer_pct" else f"{v:,.0f}") for v in row]
                  for row in z], texttemplate="%{text}", colorbar=dict(title=labels[metric]),
            hovertemplate="From %{y} → to %{x}<br>" + labels[metric] + ": %{z:,.1f}<br>people: %{customdata:,}<extra></extra>"))
        st.plotly_chart(style(fig, 560 if level == "state" else 640).update_layout(
            title=f"Grid: from {lname} (rows) → to {lname} (columns), busiest {n_top} of each",
            yaxis=dict(autorange="reversed"), xaxis_title=f"Going to ({lname})", yaxis_title=f"Starting from ({lname})",
            xaxis=dict(tickangle=-40)), width="stretch")
        st.caption("A → B and B → A are separate boxes. Empty box = no trips. Trips before May-2024 have no route "
                   "data and are not shown here.")
        with st.expander("Full table"):
            st.dataframe(mx.sort_values("journeys", ascending=False), width="stretch", hide_index=True)
        download(mx.sort_values("journeys", ascending=False), f"{lname}_trips_{hm_state.split(' ')[0]}")

# ---------------------------------------------------------------- 5. popular routes
with tabs[4]:
    lvl = st.radio("Route level", ["Town → town", "Stop → stop"], horizontal=True)
    rt = R["routes"] if lvl == "Town → town" else R["stops"]
    order = st.radio("Rank by", ["completed_journeys", "unique_customers", "route_regular_customers", "repeat_customer_pct"],
                     horizontal=True, format_func=lambda x: x.replace("_", " ").capitalize())
    min_c = st.slider("Minimum unique customers on route", 1, 200, 20 if order == "repeat_customer_pct" else 5)
    rk = rt[rt.unique_customers >= min_c].sort_values(order, ascending=False)
    t20 = rk.head(20).iloc[::-1]
    fig = px.bar(t20, x=order, y="route", orientation="h", text=order,
                 custom_data=["unique_customers", "completed_journeys", "repeat_customer_pct", "route_regular_customers"])
    fig.update_traces(marker_color=BLUE, textposition="outside",
                      texttemplate="%{text:.1f}%" if order == "repeat_customer_pct" else "%{text:,}",
                      hovertemplate="%{y}<br>%{customdata[0]:,} customers · %{customdata[1]:,} journeys<br>"
                                    "%{customdata[2]:.1f}% repeat · %{customdata[3]:,} route-regulars<extra></extra>")
    st.plotly_chart(style(fig, 640).update_layout(title=f"Top 20 routes by {order.replace('_', ' ')}",
                                                  xaxis_title=None, yaxis_title=None), width="stretch")
    st.caption(f"Route-regular = customer with ≥{M.ROUTE_REGULAR_MIN_TRIPS} journeys on that directed route. "
               "Repeat booking rate = share of the route's journeys that were a customer's 2nd+ trip on it. "
               "Stop names are normalised (spacing/case); raw examples are kept in the table.")
    st.dataframe(rk, width="stretch", hide_index=True)
    download(rk, "routes_" + ("town" if lvl == "Town → town" else "stop"))

# ---------------------------------------------------------------- 6. service comparison
with tabs[5]:
    mo = R["monthly"].copy()
    mo["month"] = pd.to_datetime(mo.month)
    a, b = st.columns(2)
    for col, ycol, title in ((a, "journeys", "Completed journeys per month"), (b, "customers", "Active customers per month")):
        fig = px.line(mo, x="month", y=ycol, color="service", color_discrete_map=SVC_COLORS)
        fig.update_traces(line=dict(width=2), hovertemplate="%{x|%b %Y}: %{y:,}<extra>%{fullData.name}</extra>")
        col.plotly_chart(style(fig, 360).update_layout(title=title, xaxis_title=None, yaxis_title=None,
                                                       hovermode="x unified"), width="stretch")
    c = f[f.completed]
    comp = c.groupby("service").agg(customers=("customer_key", "nunique"), journeys=("customer_key", "size"),
                                    first=("journey_date", "min"), last=("journey_date", "max")).reset_index()
    comp["journeys_per_customer"] = (comp.journeys / comp.customers).round(2)
    st.dataframe(comp, width="stretch", hide_index=True)
    ch = c.groupby(["channel", "service"]).size().rename("journeys").reset_index()
    fig = px.bar(ch, x="journeys", y="channel", color="service", orientation="h", color_discrete_map=SVC_COLORS,
                 barmode="stack")
    fig.update_traces(hovertemplate="%{y} · %{fullData.name}: %{x:,} journeys<extra></extra>",
                      marker_line_color="white", marker_line_width=2)
    st.plotly_chart(style(fig, 340).update_layout(title="Journeys by booking channel and service",
                                                  xaxis_title=None, yaxis_title=None), width="stretch")
    st.caption("Green Card usage stops after Feb 2025 in the data (last pass purchase 2025-02-08).")
    download(R["monthly"], "service_monthly")

# ---------------------------------------------------------------- 7. frequency
with tabs[6]:
    fr = R["freq"]
    a, b = st.columns(2)
    fig = px.bar(fr, x="frequency_band", y="customers", text="customers", custom_data=["customer_pct"])
    fig.update_traces(marker_color=BLUE, texttemplate="%{text:,}", textposition="outside",
                      hovertemplate="%{x}: %{y:,} customers (%{customdata[0]}%)<extra></extra>")
    a.plotly_chart(style(fig, 380).update_layout(title="Customers by completed journeys", xaxis_title=None,
                                                 yaxis_title=None), width="stretch")
    fig = px.bar(fr, x="frequency_band", y="journey_pct", text="journey_pct")
    fig.update_traces(marker_color=BLUE, texttemplate="%{text:.1f}%", textposition="outside",
                      hovertemplate="%{x}: %{y:.1f}% of all journeys<extra></extra>")
    b.plotly_chart(style(fig, 380).update_layout(title="Share of all journeys taken by each band",
                                                 xaxis_title=None, yaxis_title=None), width="stretch")
    st.dataframe(fr, width="stretch", hide_index=True)
    download(fr, "frequency_bands")

# ---------------------------------------------------------------- 8. recent activity
with tabs[7]:
    sg = R["seg"]
    st.caption(f"Recency window = {M.RECENCY_DAYS} days before {M.AS_OF.date()} (≈85th percentile of the gap between "
               f"a repeat customer's trips; median gap is 11 days). 'Previously regular – inactive' = active in "
               f"≥{M.REGULAR_MIN_MONTHS} months or ≥{M.HIGH_FREQ_MIN} journeys, no journey in the window. "
               "Nobody is labelled churned — inactive only means no journey inside the window.")
    fig = px.bar(sg, x="customers", y="segment", orientation="h", text="customers", custom_data=["customer_pct", "avg_journeys"])
    fig.update_traces(marker_color=BLUE, texttemplate="%{text:,}", textposition="outside",
                      hovertemplate="%{y}: %{x:,} customers (%{customdata[0]}%) · avg %{customdata[1]} journeys<extra></extra>")
    st.plotly_chart(style(fig, 340).update_layout(title="Recency × frequency segments", xaxis_title=None,
                                                  yaxis_title=None, yaxis=dict(autorange="reversed")), width="stretch")
    st.dataframe(sg, width="stretch", hide_index=True)
    lapsed = prof[prof.segment == "Previously regular – inactive"].reset_index()
    top_rt = (f[f.completed & (f.town_route != M.UNMAPPED_LEGACY)].groupby(["customer_key", "town_route"]).size()
              .rename("trips").reset_index().sort_values("trips", ascending=False).drop_duplicates("customer_key"))
    lapsed = lapsed.merge(top_rt, on="customer_key", how="left")
    st.markdown("**Previously regular customers now inactive — by their most-travelled route**")
    lr_routes = lapsed.groupby("town_route").agg(customers=("customer_key", "size"),
                                                 last_seen_median=("last_journey", "median")).reset_index()
    st.dataframe(lr_routes.sort_values("customers", ascending=False).head(50), width="stretch", hide_index=True)
    out = lapsed[["customer_key", "journeys", "active_months", "first_journey", "last_journey", "services",
                  "primary_boarding_state", "town_route", "trips"]].rename(columns={"customer_key": "customer_id_anon"})
    download(out, "previously_regular_inactive_anon", "Download anonymised win-back list")

# ---------------------------------------------------------------- 9. definitions
with tabs[8]:
    p = os.path.join(M.HERE, "DATA_DICTIONARY.md")
    st.markdown(open(p).read() if os.path.exists(p) else "Data dictionary not found.")
