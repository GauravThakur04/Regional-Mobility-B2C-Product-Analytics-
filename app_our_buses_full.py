"""Our buses dashboard (ticket_ticketnew.source = 1).  Run:  streamlit run app.py
Everything is computed through our_buses.py + metrics.py. Customer ids shown are anonymised."""
import os
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import metrics as M
import our_buses as O

st.set_page_config(page_title="Our Buses — Customers", layout="wide")
M.set_scope("source1")

# Categorical slots in fixed order (validated palette); channel colour follows the channel, never its rank.
CH_COLORS = {"App": "#2a78d6", "Green Card": "#eb6834", "Website": "#1baf7a", "App (old system)": "#9ec5f4", "Other": "#a8a7a1"}
BLUE = "#2a78d6"
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
FONT = dict(family="Inter, system-ui, sans-serif", size=13, color="#0b0b0b")


def style(fig, h=380):
    fig.update_layout(template="plotly_white", height=h, font=FONT, margin=dict(l=10, r=10, t=44, b=10),
                      hoverlabel=dict(bgcolor="white", font_size=12), legend=dict(orientation="h", y=1.1, x=0, title=None),
                      bargap=0.25)
    fig.update_xaxes(gridcolor="#ecebe8", zeroline=False, linecolor="#c3c2b7")
    fig.update_yaxes(gridcolor="#ecebe8", zeroline=False, linecolor="#c3c2b7")
    fig.update_traces(marker_line_width=0, selector=dict(type="bar"))
    return fig


def download(df, name, label="Download CSV"):
    st.download_button(label, df.to_csv(index=False).encode(), f"{name}.csv", "text/csv", key=f"dl_{name}")


def bar_h(df, x, y, title, h=420, pct=False, color=BLUE, hover=None):
    fig = px.bar(df, x=x, y=y, orientation="h", text=x)
    fig.update_traces(marker_color=color, textposition="outside",
                      texttemplate="%{text:.1f}%" if pct else "%{text:,}",
                      hovertemplate=hover or ("%{y}: %{x:.1f}%<extra></extra>" if pct else "%{y}: %{x:,}<extra></extra>"))
    return style(fig, h).update_layout(title=title, xaxis_title=None, yaxis_title=None)


def anon(s):
    return "C" + s.astype(str).str[:12]


@st.cache_data(show_spinner="Loading our-bus tickets…")
def load():
    t, j = O.build()
    keep_t = ["ticket_id", "customer_key", "attempt", "valid", "status", "channel", "era", "journey_date", "booking_date",
              "from_state", "to_state", "cancelled_by", "town_route", "is_test_user", "is_deleted"]
    return t[keep_t].copy(), j


@st.cache_data
def compute(j):
    M.set_scope("source1")
    prof = M.customer_profile(j)
    return dict(prof=prof, routes=M.route_table(j, "town"), stops=M.route_table(j, "stop", min_customers=3),
                freq=M.frequency_table(prof), seg=M.segment_table(prof))


@st.cache_data
def cohort_for(j):
    M.set_scope("source1")
    return M.cohort_tables(j, max_k=12)


@st.cache_data
def matrix_for(j, level):
    M.set_scope("source1")
    return M.state_route_matrix(j, level)


T, J = load()

# ---------------------------------------------------------------- header + filters (one row)
st.title("Our buses — who books, how, and where")
st.caption("Source: ab_commuter (read-only), **ticket_ticketnew where source = 1**. A booking counts when it was paid "
           "online (App / Website) or booked with the **Green Card** (the card is the payment). Unpaid app/website "
           f"checkouts are not counted as trips. Completed = travel date before {M.AS_OF.date()}. "
           "Tickets from the old system (Dec-2021 → May-2024) have no route, district or operator.")

f1, f2, f3, f4 = st.columns([1.8, 2.2, 1.8, 2.4])
dmin, dmax = J.journey_date.min().date(), J.journey_date.max().date()
dr = f1.date_input("Travel dates", (dmin, dmax), min_value=dmin, max_value=dmax)
st_counts = pd.concat([J.from_state, J.to_state]).value_counts()
state_list = [s for s in st_counts.index if s not in (M.UNMAPPED, M.UNMAPPED_LEGACY)]
sel_states = f2.multiselect("State (trip starts or ends here)", state_list, placeholder="All states",
                            help="Tip: pick Punjab, Haryana and Himachal Pradesh to focus on those three.")
present = [c for c in O.CHANNELS if c in set(J.channel)]
sel_ch = f3.multiselect("How booked", present, placeholder="All channels")
routes_all = J.town_route[J.town_route != M.UNMAPPED_LEGACY].value_counts().index[:3000].tolist()
sel_routes = f4.multiselect("Route (town → town)", routes_all, placeholder="All routes")


def apply_filters(df, date_col="journey_date"):
    if isinstance(dr, (tuple, list)) and len(dr) == 2:
        df = df[(df[date_col] >= pd.Timestamp(dr[0])) & (df[date_col] <= pd.Timestamp(dr[1]))]
    if sel_states:
        df = df[df.from_state.isin(sel_states) | df.to_state.isin(sel_states)]
    if sel_ch:
        df = df[df.channel.isin(sel_ch)]
    if sel_routes:
        df = df[df.town_route.isin(sel_routes)]
    return df


f = apply_filters(J)
ft = apply_filters(T)
c = f[f.completed]
if c.empty:
    st.warning("No completed trips match these filters.")
    st.stop()
if sel_states:
    st.info(f"Showing trips that start or end in **{', '.join(sel_states)}**. Old-system tickets (2021–24) have no "
            "state, so they drop out when a state is picked.")
R = compute(f)
prof = R["prof"]

tabs = st.tabs(["Overview", "How people book", "Regular customers", "Do they come back?", "Where they travel",
                "Top routes", "Operators & buses", "Cancellations", "Definitions"])

# ---------------------------------------------------------------- 1. overview
with tabs[0]:
    k = st.columns(5)
    k[0].metric("People who travelled", f"{c.customer_key.nunique():,}")
    k[1].metric("Trips taken", f"{len(c):,}")
    k[2].metric("Came back (2+ trips)", f"{int(prof.is_repeat.sum()):,}", f"{100 * prof.is_repeat.mean():.1f}%", delta_color="off")
    k[3].metric("Regulars (3+ different months)", f"{int(prof.is_regular.sum()):,}", f"{100 * prof.is_regular.mean():.1f}%", delta_color="off")
    k[4].metric("Used the Green Card", f"{c[c.channel == 'Green Card'].customer_key.nunique():,}")

    a, b = st.columns([1, 1.6])
    byc = (c.groupby("channel").agg(people=("customer_key", "nunique"), trips=("customer_key", "size"))
           .reindex([x for x in O.CHANNELS if x in set(c.channel)]).reset_index())
    fig = px.bar(byc.iloc[::-1], x="trips", y="channel", orientation="h", text="trips", color="channel",
                 color_discrete_map=CH_COLORS, custom_data=["people"])
    fig.update_traces(texttemplate="%{text:,}", textposition="outside",
                      hovertemplate="%{y}: %{x:,} trips · %{customdata[0]:,} people<extra></extra>")
    a.plotly_chart(style(fig, 320).update_layout(title="Trips by how they were booked", showlegend=False,
                                                 xaxis_title=None, yaxis_title=None), width="stretch")
    m = c.groupby(["month", "channel"]).size().rename("trips").reset_index()
    m["month"] = m.month.dt.to_timestamp()
    fig = px.bar(m, x="month", y="trips", color="channel", color_discrete_map=CH_COLORS,
                 category_orders={"channel": O.CHANNELS})
    fig.update_traces(hovertemplate="%{x|%b %Y}: %{y:,} trips<extra>%{fullData.name}</extra>",
                      marker_line_color="white", marker_line_width=1)
    b.plotly_chart(style(fig, 320).update_layout(title="Trips per month, by how booked", xaxis_title=None,
                                                 yaxis_title=None, barmode="stack", hovermode="x unified"), width="stretch")
    yr = c.groupby(c.journey_date.dt.year).agg(trips=("customer_key", "size"), people=("customer_key", "nunique"))
    peak = c.groupby("month").size()
    last12 = c[c.journey_date >= M.AS_OF - pd.DateOffset(months=12)]
    st.markdown(
        f"**What this shows.** Busiest month: **{peak.idxmax().strftime('%b %Y')}** with {peak.max():,} trips. "
        f"In the last 12 months there were **{len(last12):,} trips by {last12.customer_key.nunique():,} people**. "
        "Our-bus bookings in this table almost stop after Dec-2024, the month the Green Card stops appearing.")
    st.dataframe(yr.rename_axis("year").reset_index(), width="content", hide_index=True)

# ---------------------------------------------------------------- 2. how people book
with tabs[1]:
    st.subheader("How people book — and how many finish")
    cur = ft[ft.attempt & (ft.era == "Current app (2024 →)")]
    fun = (cur.groupby("channel").agg(started=("ticket_id", "size"), completed=("valid", "sum"),
                                      people_started=("customer_key", "nunique"))
           .reindex([x for x in ["App", "Website", "Green Card", "Other"] if x in set(cur.channel)]).reset_index())
    fun["completed_%"] = (100 * fun.completed / fun.started).round(1)
    if len(fun):
        fl = fun.melt(id_vars="channel", value_vars=["started", "completed"], var_name="stage", value_name="bookings")
        fig = px.bar(fl, x="bookings", y="channel", color="stage", orientation="h", barmode="group", text="bookings",
                     color_discrete_map={"started": "#cde2fb", "completed": BLUE})
        fig.update_traces(texttemplate="%{text:,}", textposition="outside",
                          hovertemplate="%{y} · %{fullData.name}: %{x:,}<extra></extra>")
        st.plotly_chart(style(fig, 300).update_layout(title="Bookings started vs completed (2024 onward)",
                                                      xaxis_title=None, yaxis_title=None), width="stretch")
        st.caption("A Green Card booking needs no online payment, so it always counts as completed. App and website "
                   "bookings only count once paid; the rest are abandoned checkouts.")
        st.dataframe(fun, width="content", hide_index=True)
    ce = c[c.era == "Current app (2024 →)"]
    if len(ce):
        a, b = st.columns(2)
        lead = pd.cut(ce.lead_days.clip(lower=0), [-1, 0, 1, 3, 7, 10**4],
                      labels=["Same day", "1 day before", "2–3 days", "4–7 days", "8+ days"]).value_counts(sort=False)
        lead = (100 * lead / lead.sum()).rename("pct").reset_index().rename(columns={"lead_days": "when"})
        fig = px.bar(lead, x="when", y="pct", text="pct")
        fig.update_traces(marker_color=BLUE, texttemplate="%{text:.0f}%", textposition="outside",
                          hovertemplate="%{x}: %{y:.1f}% of trips<extra></extra>")
        a.plotly_chart(style(fig, 320).update_layout(title="How far ahead people book", xaxis_title=None,
                                                     yaxis_title="% of trips", yaxis=dict(ticksuffix="%")), width="stretch")
        kb = ce.km_band.value_counts(sort=False).reindex(O.KM_ORDER[:-1])
        kb = (100 * kb / kb.sum()).rename("pct").reset_index().rename(columns={"km_band": "distance"})
        fig = px.bar(kb, x="distance", y="pct", text="pct")
        fig.update_traces(marker_color=BLUE, texttemplate="%{text:.0f}%", textposition="outside",
                          hovertemplate="%{x}: %{y:.1f}% of trips<extra></extra>")
        b.plotly_chart(style(fig, 320).update_layout(title="Trip length", xaxis_title=None,
                                                     yaxis_title="% of trips", yaxis=dict(ticksuffix="%")), width="stretch")
        a, b = st.columns(2)
        hr = ce.book_hour.value_counts().reindex(range(24), fill_value=0).rename("trips").reset_index().rename(columns={"book_hour": "hour"})
        fig = px.bar(hr, x="hour", y="trips")
        fig.update_traces(marker_color=BLUE, hovertemplate="%{x}:00–%{x}:59 · %{y:,} bookings<extra></extra>")
        a.plotly_chart(style(fig, 300).update_layout(title="Time of day people book", xaxis_title="Hour (IST)",
                                                     yaxis_title=None, xaxis=dict(dtick=2)), width="stretch")
        dw = ce.travel_dow.value_counts(sort=False).rename("trips").reset_index().rename(columns={"travel_dow": "day"})
        fig = px.bar(dw, x="day", y="trips", text="trips")
        fig.update_traces(marker_color=BLUE, texttemplate="%{text:,}", textposition="outside",
                          hovertemplate="%{x}: %{y:,} trips<extra></extra>")
        b.plotly_chart(style(fig, 300).update_layout(title="Day of travel", xaxis_title=None, yaxis_title=None), width="stretch")
        fares = (c.groupby("channel").payable_amount.agg(["count", "median", "mean"]).round(0)
                 .rename(columns={"count": "trips", "median": "median_fare_₹", "mean": "average_fare_₹"}).reset_index())
        st.markdown("**Fares by how booked**")
        st.dataframe(fares, width="content", hide_index=True)

# ---------------------------------------------------------------- 3. regular customers
with tabs[2]:
    st.subheader("Who books regularly?")
    fr = R["freq"]
    a, b = st.columns(2)
    fig = px.bar(fr, x="frequency_band", y="customers", text="customers", custom_data=["customer_pct"])
    fig.update_traces(marker_color=BLUE, texttemplate="%{text:,}", textposition="outside",
                      hovertemplate="%{x}: %{y:,} people (%{customdata[0]}%)<extra></extra>")
    a.plotly_chart(style(fig, 340).update_layout(title="People by number of trips", xaxis_title=None, yaxis_title=None), width="stretch")
    fig = px.bar(fr, x="frequency_band", y="journey_pct", text="journey_pct")
    fig.update_traces(marker_color=BLUE, texttemplate="%{text:.0f}%", textposition="outside",
                      hovertemplate="%{x}: %{y:.1f}% of all trips<extra></extra>")
    b.plotly_chart(style(fig, 340).update_layout(title="Share of all trips they take", xaxis_title=None,
                                                 yaxis_title=None, yaxis=dict(ticksuffix="%")), width="stretch")
    regs = prof[prof.is_regular | (prof.journeys >= M.HIGH_FREQ_MIN)].reset_index()
    tr = (c[c.town_route != M.UNMAPPED_LEGACY].groupby(["customer_key", "town_route"]).size().rename("trips_on_route")
          .reset_index().sort_values("trips_on_route", ascending=False).drop_duplicates("customer_key"))
    regs = regs.merge(tr, on="customer_key", how="left")
    st.markdown(f"**{len(regs):,} regular customers** (travelled in 3+ different months or took 6+ trips). "
                "Their most-used routes:")
    rr = (regs.dropna(subset=["town_route"]).groupby("town_route")
          .agg(regular_people=("customer_key", "size"), avg_trips=("journeys", "mean"),
               used_green_card=("gc_journeys", lambda s: int((s > 0).sum())), last_trip=("last_journey", "max"))
          .round(1).reset_index().sort_values("regular_people", ascending=False))
    rr["last_trip"] = rr.last_trip.dt.date
    st.dataframe(rr.head(30), width="stretch", hide_index=True)
    out = regs.assign(customer_id_anon=anon(regs.customer_key))[
        ["customer_id_anon", "journeys", "active_months", "first_journey", "last_journey", "services", "town_route", "trips_on_route"]]
    download(out, "regular_customers_anon", "Download anonymised regulars list")
    st.markdown("**Are they still travelling?** (90-day window)")
    st.dataframe(R["seg"], width="content", hide_index=True)

# ---------------------------------------------------------------- 4. cohorts
with tabs[3]:
    st.subheader("Do new customers come back?")
    c1, c2, c3 = st.columns([2, 1.2, 1.2])
    opts = [s for s in state_list if s in set(f.from_state) | set(f.to_state)]
    coh_state = c1.selectbox("State (trip starts or ends here)", ["All states"] + opts, key="coh_state")
    horizon = c2.radio("Look ahead", [6, 12], format_func=lambda x: f"{x} months", horizontal=True, key="coh_h")
    min_n = c3.number_input("Hide groups smaller than", 0, 5000, 20, step=5, key="coh_min",
                            help="Very small groups give jumpy percentages (1 person out of 3 = 33%).")
    fc = f if coh_state == "All states" else f[(f.from_state == coh_state) | (f.to_state == coh_state)]
    if fc[fc.completed].empty:
        st.info("No completed trips for this state with the current filters.")
    else:
        summ, ret = cohort_for(fc)
        size = summ.set_index("cohort_month").new_customers
        ks = [k for k in range(1, horizon + 1) if k in ret.columns]
        r = ret.loc[ret.index.isin(size[size >= min_n].index), ks]
        where = "" if coh_state == "All states" else f" to/from {coh_state}"
        ex = summ[(summ.new_customers >= min_n) & summ.m1_retention_pct.notna() & summ.m3_retention_pct.notna()]
        example = ""
        if len(ex):
            e = ex.sort_values("new_customers").iloc[-1]
            example = (f"**Example:** {int(e.new_customers):,} people took their first trip{where} in "
                       f"**{pd.Period(e.cohort_month).strftime('%b %Y')}**. **{e.m1_retention_pct:.1f}%** travelled again "
                       f"1 month later and **{e.m3_retention_pct:.1f}%** 3 months later.")
        st.info("**How to read this.** We group people by the month of their *first* trip, then check what share "
                "travelled again 1, 2, 3… months later. Higher = more loyal.  \n" + example)
        sz = size.reindex(r.index)
        avg = [((r[k] * sz)[r[k].notna()].sum() / sz[r[k].notna()].sum()) if r[k].notna().any() else None for k in ks]
        av = pd.DataFrame({"when": [f"After {k} mo" for k in ks], "pct": avg}).dropna()
        fig = px.bar(av, x="when", y="pct", text="pct")
        fig.update_traces(marker_color=BLUE, texttemplate="%{text:.1f}%", textposition="outside",
                          hovertemplate="%{x}: %{y:.1f}% travelled again<extra></extra>")
        st.plotly_chart(style(fig, 300).update_layout(title=f"On average, what % of new customers{where} travel again?",
                                                      xaxis_title=None, yaxis_title=None, yaxis=dict(ticksuffix="%")), width="stretch")
        if len(r):
            start = st.select_slider("Show groups starting from", options=list(r.index), key="coh_start",
                                     value="2024-03" if "2024-03" in r.index else r.index[0])
            rr = r.loc[start:]
            ylab = [f"{pd.Period(i).strftime('%b %Y')} · {int(size[i]):,} people" for i in rr.index]
            zmax = rr.max().max()
            fig = go.Figure(go.Heatmap(
                z=rr.values, x=[f"After {k} mo" for k in rr.columns], y=ylab, colorscale=SEQ, zmin=0,
                zmax=max(10, float(zmax) if pd.notna(zmax) else 0),
                text=[["" if pd.isna(v) else f"{v:.0f}%" for v in row] for row in rr.values], texttemplate="%{text}",
                colorbar=dict(title="% came back", ticksuffix="%"),
                hovertemplate="First trip: %{y}<br>%{x}: %{z:.1f}% travelled again<extra></extra>"))
            st.plotly_chart(style(fig, max(360, 26 * len(rr) + 120)).update_layout(
                title="Each row = people whose first trip was in that month · darker = more came back",
                yaxis=dict(autorange="reversed")), width="stretch")
            st.caption(f"Empty boxes = that month hasn't happened yet. Groups under {min_n} people are hidden.")
        with st.expander("Full table"):
            st.dataframe(summ, width="stretch", hide_index=True)
        download(summ, "cohorts")

# ---------------------------------------------------------------- 5. where they travel (district heatmap)
with tabs[4]:
    st.subheader("Where do our customers travel from and to?")
    opts = [s for s in state_list if s in set(f.from_state) | set(f.to_state)]
    h1, h2 = st.columns([2, 3])
    hm_state = h1.selectbox("State", opts, key="hm_state", help="Districts of this state; other states show as one box.")
    labels = {"unique_customers": "Number of people", "repeat_customer_pct": "% who travelled it again",
              "regular_customers": f"Regular riders ({M.ROUTE_REGULAR_MIN_TRIPS}+ trips)"}
    metric = h2.radio("Show in each box", list(labels), horizontal=True, format_func=labels.get, key="hm_metric")
    src = f[(f.from_state == hm_state) | (f.to_state == hm_state)].copy()
    for side in ("from", "to"):
        dist = src[f"{side}_region"].str.replace(r" \([^)]*\)$", "", regex=True)
        src[f"{side}_lbl"] = dist.where(src[f"{side}_state"] == hm_state, src[f"{side}_state"])
    mx = matrix_for(src, "lbl")
    oc, dc = "origin_lbl", "destination_lbl"
    mx = mx[~mx[oc].isin([M.UNMAPPED, M.UNMAPPED_LEGACY]) & ~mx[dc].isin([M.UNMAPPED, M.UNMAPPED_LEGACY])]
    if mx.empty:
        st.info("No trips with route data for this selection.")
    else:
        best = mx.sort_values("unique_customers", ascending=False).iloc[0]
        st.info(f"**How to read this.** Each **row** is where people start, each **column** is where they go. "
                f"Districts are in {hm_state}; other states show as one box. Darker = bigger number.  \n"
                f"**Busiest:** {best[oc]} → {best[dc]}: {int(best.unique_customers):,} people, {int(best.journeys):,} trips, "
                f"{best.repeat_customer_pct:.0f}% travelled it again. A box on the diagonal is travel inside one district.")
        t10 = mx.sort_values(metric, ascending=False)
        if metric == "repeat_customer_pct":
            t10 = t10[t10.unique_customers >= 30]
        t10 = t10.head(10).assign(trip=lambda d: d[oc] + " → " + d[dc]).iloc[::-1]
        st.plotly_chart(bar_h(t10, metric, "trip", f"Top 10 trips — {labels[metric].lower()}"
                              + (" (30+ people)" if metric == "repeat_customer_pct" else ""),
                              pct=metric == "repeat_customer_pct"), width="stretch")
        topo = mx.groupby(oc).unique_customers.sum().nlargest(15).index
        topd = mx.groupby(dc).unique_customers.sum().nlargest(15).index
        sub = mx[mx[oc].isin(topo) & mx[dc].isin(topd)]
        pv = sub.pivot(index=oc, columns=dc, values=metric).reindex(index=topo, columns=topd)
        pc = sub.pivot(index=oc, columns=dc, values="unique_customers").reindex(index=topo, columns=topd)
        fig = go.Figure(go.Heatmap(
            z=pv.values, x=pv.columns, y=pv.index, colorscale=SEQ, customdata=pc.values,
            text=[["" if pd.isna(v) else (f"{v:.0f}%" if metric == "repeat_customer_pct" else f"{v:,.0f}") for v in row]
                  for row in pv.values], texttemplate="%{text}", colorbar=dict(title=labels[metric]),
            hovertemplate="From %{y} → to %{x}<br>" + labels[metric] + ": %{z:,.1f}<br>people: %{customdata:,}<extra></extra>"))
        st.plotly_chart(style(fig, 640).update_layout(
            title="Grid: starting from (rows) → going to (columns), busiest 15 of each",
            yaxis=dict(autorange="reversed"), xaxis=dict(tickangle=-40)), width="stretch")
        with st.expander("Full table"):
            st.dataframe(mx.sort_values("journeys", ascending=False), width="stretch", hide_index=True)
        download(mx, f"district_trips_{hm_state.replace(' ', '_')}")

# ---------------------------------------------------------------- 6. routes
with tabs[5]:
    lvl = st.radio("Route level", ["Town → town", "Stop → stop"], horizontal=True)
    rt = R["routes"] if lvl == "Town → town" else R["stops"]
    order = st.radio("Rank by", ["completed_journeys", "unique_customers", "route_regular_customers", "repeat_customer_pct"],
                     horizontal=True, format_func=lambda x: {"completed_journeys": "Trips", "unique_customers": "People",
                                                             "route_regular_customers": "Regular riders",
                                                             "repeat_customer_pct": "% who came back"}[x])
    min_c = st.slider("Only routes with at least this many people", 1, 200, 20 if order == "repeat_customer_pct" else 5)
    rk = rt[rt.unique_customers >= min_c].sort_values(order, ascending=False)
    st.plotly_chart(bar_h(rk.head(20).iloc[::-1], order, "route", "Top 20 routes", h=620,
                          pct=order == "repeat_customer_pct"), width="stretch")
    rk = rk.rename(columns={"long_route_journeys": "app_web_journeys"})
    st.dataframe(rk, width="stretch", hide_index=True)
    download(rk, "routes")

# ---------------------------------------------------------------- 7. operators & buses
with tabs[6]:
    st.subheader("Which of our operators and buses carry them?")
    ce = c[c.operator != "Unknown (old system)"]
    if ce.empty:
        st.info("Operator and bus are only known for trips from 2024 onward.")
    else:
        k = st.columns(3)
        k[0].metric("Operators", f"{ce.operator.nunique():,}")
        k[1].metric("Buses", f"{ce.bus_number.nunique():,}")
        k[2].metric("Trips on buses with a ticket machine", f"{100 * (ce.bus_has_machine == 'Bus has ticket machine').mean():.0f}%")
        op = ce.groupby(["operator", "channel"]).size().rename("trips").reset_index()
        top = ce.operator.value_counts().head(15).index
        fig = px.bar(op[op.operator.isin(top)], x="trips", y="operator", color="channel", orientation="h",
                     color_discrete_map=CH_COLORS, category_orders={"operator": list(top), "channel": O.CHANNELS})
        fig.update_traces(hovertemplate="%{y} · %{fullData.name}: %{x:,} trips<extra></extra>",
                          marker_line_color="white", marker_line_width=1)
        st.plotly_chart(style(fig, 520).update_layout(title="Top 15 operators by trips, split by how booked",
                                                      barmode="stack", xaxis_title=None, yaxis_title=None), width="stretch")
        tbl = (ce.groupby("operator").agg(trips=("customer_key", "size"), people=("customer_key", "nunique"),
                                          buses=("bus_number", "nunique"),
                                          green_card_trips=("channel", lambda s: int((s == "Green Card").sum())),
                                          first_trip=("journey_date", "min"), last_trip=("journey_date", "max"))
               .sort_values("trips", ascending=False).reset_index())
        tbl["first_trip"] = tbl.first_trip.dt.date; tbl["last_trip"] = tbl.last_trip.dt.date
        st.dataframe(tbl, width="stretch", hide_index=True)
        download(tbl, "operators")

# ---------------------------------------------------------------- 8. cancellations
with tabs[7]:
    st.subheader("Cancellations")
    cc = ft[(ft.status == 3) & ~ft.is_test_user & ~ft.is_deleted]          # status 3 = cancelled
    conf = ft[ft.valid]
    k = st.columns(3)
    k[0].metric("Cancelled tickets", f"{len(cc):,}")
    k[1].metric("Cancellation rate", f"{100 * len(cc) / max(len(cc) + len(conf), 1):.1f}%",
                help="Cancelled ÷ (cancelled + valid bookings).")
    k[2].metric("People who cancelled", f"{cc.customer_key.nunique():,}")
    if len(cc):
        who = cc.cancelled_by.fillna("Not recorded").str.title().replace({"Apnibus": "ApniBus"}).value_counts().rename("tickets").reset_index()
        a, b = st.columns([1, 1.6])
        a.plotly_chart(bar_h(who.iloc[::-1], "tickets", "cancelled_by", "Who cancelled", h=280), width="stretch")
        cm = cc.groupby(cc.journey_date.dt.to_period("M")).size().rename("cancelled").reset_index()
        cm["month"] = cm.journey_date.dt.to_timestamp()
        fig = px.bar(cm, x="month", y="cancelled")
        fig.update_traces(marker_color=BLUE, hovertemplate="%{x|%b %Y}: %{y:,} cancelled<extra></extra>")
        b.plotly_chart(style(fig, 280).update_layout(title="Cancelled tickets by travel month", xaxis_title=None,
                                                     yaxis_title=None), width="stretch")

# ---------------------------------------------------------------- 9. definitions
with tabs[8]:
    st.markdown(f"""
**Data:** `ticket_ticketnew` where `source = 1` (our buses), read-only. As-of date {M.AS_OF.date()}.

| Term | Meaning |
|---|---|
| **How booked** | **Green Card** = `ticket_with_pass` (card is the payment) · **App** = `ticket_sourcing 2`, paid online · **Website** = `ticket_sourcing 1`, paid online · **App (old system)** = migrated Dec-2021 → May-2024 tickets |
| **Trip** | A valid booking, de-duplicated per person + date + route + bus service. Completed = travel date before the as-of date. |
| **Not counted** | App/website checkouts that were never paid; cancelled tickets; test users. |
| **Person** | One phone number (shown only as an anonymised `C…` id). |
| **Came back** | 2+ trips. **Regular** = trips in 3+ different months (or 6+ trips on the Regular customers tab). |
| **Route / district / state** | From the ticket's towns. Old-system tickets have none. |
| **Operator & bus** | Ticket → bus service → bus number → bus record (2024 onward). "Ticket machine" = bus marked `is_pos_connected`. |
| **Trip length** | `distance_in_km` when recorded, else estimated from town coordinates × 1.25. |

**Known gaps:** tickets cut on the conductor's machine with the Green Card are **not** stored in this database. Only
Green Card bookings made in the app are. Bookings in this table almost stop after Dec-2024.
""")
