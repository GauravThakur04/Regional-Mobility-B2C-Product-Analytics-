"""Apnibus passenger dashboard — who travels, on which routes and buses, and who keeps coming back.
Run:  streamlit run app.py
Two data sources, picked in the sidebar:
  * Green Card passengers  — apnibus-service-db.service_app_servicebooking (card tapped on the conductor's machine), via card.py
  * App & website      — ab_commuter.ticket_ticketnew WHERE source = 1 AND is_paid (our buses), via paid.py
Customer ids shown are anonymised (salted hash of the phone number); no phone numbers are loaded."""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import metrics as M
import paid as P
import card as CD

st.set_page_config(page_title="Apnibus Passenger Dashboard", layout="wide", initial_sidebar_state="expanded")
M.set_scope("paid")
M.UNMAPPED_LEGACY = P.NO_TOWN

BLUE, ORANGE = "#2a78d6", "#eb6834"                       # categorical slots 1 & 2
SVC_COLORS = {"Without Green Card": BLUE, "Green Card": ORANGE}
VIA_COLORS = {"App": BLUE, "App + Green Card": ORANGE, "Website": "#2e9e6b", "Website + Green Card": "#8a5cd1",
              "Agent": "#c9a227", "Other": "#a3a29b"}
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]   # one-hue blue ramp
BAND_COLORS = ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]               # ordinal steps 100→700
TRIP_BANDS = [(1, 1, "1 trip"), (2, 2, "2 trips"), (3, 5, "3–5 trips"), (6, 10, "6–10 trips"), (11, 10**6, "11+ trips")]
FONT = dict(family="Inter, system-ui, sans-serif", size=13, color="#0b0b0b")
LOYAL = M.ROUTE_REGULAR_MIN_TRIPS                         # 3+ trips on the same route / bus = loyal rider
STATUS = [(30, "Active (last 30 days)"), (90, "Slipping (31–90 days)"), (365, "Lapsed (3–12 months)"),
          (10**6, "Dormant (over a year)")]


def style(fig, h=380):
    fig.update_layout(template="plotly_white", height=h, font=FONT, margin=dict(l=10, r=60, t=84, b=10),
                      title=dict(x=0, xanchor="left", y=0.98, yanchor="top", pad=dict(l=4)),
                      hoverlabel=dict(bgcolor="white", font_size=12),
                      legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, xanchor="left", title=None),
                      bargap=0.25)
    fig.update_xaxes(gridcolor="#ecebe8", zeroline=False, linecolor="#c3c2b7")
    fig.update_yaxes(gridcolor="#ecebe8", zeroline=False, linecolor="#c3c2b7")
    fig.update_traces(marker_line_width=0, selector=dict(type="bar"))
    return fig


def download(df, name, label="Download CSV"):
    st.download_button(label, df.to_csv(index=False).encode(), f"{name}.csv", "text/csv", key=f"dl_{name}")


def anon(s):
    return "C" + s.astype(str).str[:12]


def band(n):
    for lo, hi, lab in TRIP_BANDS:
        if lo <= n <= hi:
            return lab


def status(days):
    for lim, lab in STATUS:
        if days <= lim:
            return lab


def explain(text):
    st.info(text, icon=":material/lightbulb:")


@st.cache_data(show_spinner="Loading app & website bookings…")
def load():
    return P.build()


@st.cache_data
def route_stats(j, level):
    M.set_scope("paid"); M.UNMAPPED_LEGACY = P.NO_TOWN
    return M.route_table(j, level)


@st.cache_data
def town_matrix(j):
    M.set_scope("paid"); M.UNMAPPED_LEGACY = P.NO_TOWN
    return M.state_route_matrix(j, "town")


@st.cache_data(show_spinner="Loading Green Card taps…")
def load_card():
    return CD.build(), CD.customers()


T, J = load()
CT, CU = load_card()


# ---------------------------------------------------------------- shared views (both data sources)
# Every shared view takes a normalised frame: one row per trip with
#   cid, date, month, route, bus, operator, state  (route / bus may hold a "not known" placeholder)

def cohort(df):
    """First-trip month per person; % of each group who travelled again k calendar months later."""
    first = df.groupby("cid").month.min().rename("first")
    act = df[["cid", "month"]].drop_duplicates().join(first, on="cid")
    act["k"] = (act.month.dt.year - act["first"].dt.year) * 12 + (act.month.dt.month - act["first"].dt.month)
    size = first.value_counts().sort_index()
    ret = act.groupby(["first", "k"]).cid.nunique().unstack().reindex(size.index)
    ret = 100 * ret.div(size, axis=0)
    for g in ret.index:                                   # months that haven't finished yet stay blank
        ret.loc[g, [k for k in ret.columns if g + k > M.LAST_FULL_MONTH]] = np.nan
    return size, ret


NO_BUS = {"Unknown", "Not recorded"}


def mode_by(df, key, col, skip=()):
    """Most common value of `col` for each `key` (vectorised; ties → alphabetical)."""
    d = df[~df[col].isin(skip)] if skip else df
    m = d.groupby([key, col]).size().rename("_n").reset_index().sort_values([key, "_n", col], ascending=[True, False, True])
    return m.drop_duplicates(key).set_index(key)[col]


def route_loyalty(n):
    pr = n.groupby(["route", "cid"]).size().rename("trips").reset_index()
    rt = pr.groupby("route").agg(riders=("cid", "size"), trips=("trips", "sum"),
                                 came_back=("trips", lambda x: int((x >= 2).sum())),
                                 loyal_riders=("trips", lambda x: int((x >= LOYAL).sum()))).reset_index()
    rt["loyal_%"] = (100 * rt.loyal_riders / rt.riders).round(1)
    rt["came_back_%"] = (100 * rt.came_back / rt.riders).round(1)
    rt["trips_per_rider"] = (rt.trips / rt.riders).round(2)
    extra = n.groupby("route").agg(last_trip=("date", "max"))
    extra["buses"] = n[~n.bus.isin(NO_BUS)].groupby("route").bus.nunique()
    extra["main_operator"] = mode_by(n, "route", "operator")
    extra["state"] = mode_by(n, "route", "state")
    extra = extra.fillna({"buses": 0}).reset_index()
    rt = rt.merge(extra, on="route")
    rt["last_trip"] = rt.last_trip.dt.date
    return pr, rt


def view_loyal_routes(n, key, what):
    st.subheader("Loyal routes — where the same people travel again and again")
    explain(f"A **loyal rider** has taken the same route **{LOYAL} or more times**. Routes with many loyal riders are daily "
            f"commutes (office, college, market) — the easiest people to win back and the best routes for a monthly pass. "
            f"{what}")
    if n.empty:
        st.info("No trips with a known route for these filters.")
        return
    pr, rt = route_loyalty(n)
    g1, g2 = st.columns([1.6, 3])
    order = g1.selectbox("Rank routes by", ["loyal_riders", "loyal_%", "trips_per_rider", "riders"], key=f"{key}_lo_order",
                         format_func={"loyal_riders": f"Number of loyal riders ({LOYAL}+ trips)",
                                      "loyal_%": "Share of riders who are loyal",
                                      "trips_per_rider": "Trips per rider", "riders": "Total riders"}.get)
    min_r = g2.slider("Only routes with at least this many riders (hides tiny routes)", 1, 200,
                      1 if order in ("loyal_riders", "riders") else 20, key=f"{key}_lo_min_{order}")
    rk = rt[rt.riders >= min_r].sort_values([order, "riders"], ascending=False)
    k = st.columns(4)
    k[0].metric("Routes", f"{len(rk):,}")
    k[1].metric("Loyal riders (on these routes)", f"{int(rk.loyal_riders.sum()):,}")
    k[2].metric("Routes with 10+ loyal riders", f"{int((rk.loyal_riders >= 10).sum()):,}")
    top_loyal = rk.sort_values("loyal_riders", ascending=False).head(1)
    k[3].metric(f"Most loyal: {top_loyal.route.iloc[0]}" if len(top_loyal) else "Most loyal route",
                f"{int(top_loyal.loyal_riders.iloc[0]):,} riders" if len(top_loyal) else "—")
    if rk.empty:
        st.info("No routes this big — lower the minimum.")
        return
    top = rk.head(20).iloc[::-1]
    fig = px.bar(top, x=order, y="route", orientation="h", text=order,
                 custom_data=["riders", "loyal_riders", "loyal_%", "trips_per_rider", "main_operator"])
    fig.update_traces(marker_color=BLUE, textposition="outside", cliponaxis=False,
                      texttemplate="%{text:.0f}%" if order == "loyal_%" else
                                   ("%{text:.1f}" if order == "trips_per_rider" else "%{text:,}"),
                      hovertemplate="%{y} · %{customdata[4]}<br>%{customdata[0]:,} riders · %{customdata[1]:,} loyal "
                                    "(%{customdata[2]:.0f}%)<br>%{customdata[3]:.1f} trips per rider<extra></extra>")
    st.plotly_chart(style(fig, 130 + 26 * len(top)).update_layout(
        title=f"The {len(top)} most loyal routes", xaxis_title=None, yaxis_title=None), width="stretch")

    pr["band"] = pr.trips.map(band)
    show_routes = rk.head(15).route.tolist()
    dist = pr[pr.route.isin(show_routes)].groupby(["route", "band"]).size().rename("people").reset_index()
    dist["pct"] = 100 * dist.people / dist.groupby("route").people.transform("sum")
    fig = px.bar(dist, x="pct", y="route", color="band", orientation="h", custom_data=["people"],
                 category_orders={"band": [b[2] for b in TRIP_BANDS], "route": show_routes},
                 color_discrete_sequence=BAND_COLORS)
    fig.update_traces(hovertemplate="%{y}<br>%{fullData.name}: %{customdata[0]:,} riders (%{x:.0f}%)<extra></extra>",
                      marker_line_color="white", marker_line_width=2)
    st.plotly_chart(style(fig, 140 + 30 * len(show_routes)).update_layout(
        title="How many times each rider took the route (darker = more loyal)", barmode="stack",
        xaxis=dict(title="% of the route's riders", ticksuffix="%"), yaxis_title=None), width="stretch")

    st.markdown("**All routes, with their loyalty numbers**")
    st.dataframe(rk, width="stretch", hide_index=True,
                 column_config={"loyal_%": st.column_config.ProgressColumn("loyal_%", format="%.0f%%", min_value=0,
                                                                           max_value=100)})
    lr = n.groupby(["cid", "route"]).agg(trips=("date", "size"), first_trip=("date", "min"),
                                         last_trip=("date", "max")).reset_index()
    nb_ = n.assign(cr=n.cid + "|" + n.route)
    lr["bus"] = (lr.cid + "|" + lr.route).map(mode_by(nb_, "cr", "bus"))
    lr = lr[(lr.trips >= LOYAL) & lr.route.isin(rk.route)]
    lr = lr.assign(customer_id=anon(lr.cid), first_trip=lr.first_trip.dt.date, last_trip=lr.last_trip.dt.date)
    d1, d2 = st.columns(2)
    with d1:
        download(rk, f"{key}_loyal_routes", "Download route table (CSV)")
    with d2:
        download(lr[["customer_id", "route", "trips", "first_trip", "last_trip", "bus"]].sort_values("trips", ascending=False),
                 f"{key}_loyal_riders", f"Download loyal riders ({len(lr):,}, anonymised)")


def view_buses(n, key, note):
    st.subheader("Buses and their riders — how many customers each bus carries")
    explain("Each bar is one bus (by number plate). **Customers** = different people who travelled on it. "
            f"**Regular customers** = people who rode that same bus **{LOYAL} or more times** — the bus's own loyal base. "
            f"Pick a bus below the table to see its customers. {note}")
    nb = n[~n.bus.isin(NO_BUS)]
    if nb.empty:
        st.info("No trips with a known bus for these filters.")
        return
    pb = nb.groupby(["bus", "cid"]).size().rename("trips").reset_index()
    bt = pb.groupby("bus").agg(customers=("cid", "size"), trips=("trips", "sum"),
                               regular_customers=("trips", lambda x: int((x >= LOYAL).sum()))).reset_index()
    bt["regular_%"] = (100 * bt.regular_customers / bt.customers).round(1)
    bt["trips_per_customer"] = (bt.trips / bt.customers).round(2)
    ex = nb.groupby("bus").agg(routes=("route", "nunique"), first_trip=("date", "min"), last_trip=("date", "max"))
    for col, src in (("operator", "operator"), ("state", "state"), ("main_route", "route")):
        ex[col] = mode_by(nb, "bus", src)
    ex = ex.reset_index()
    bt = bt.merge(ex, on="bus")
    bt["first_trip"] = bt.first_trip.dt.date
    bt["last_trip"] = bt.last_trip.dt.date
    bt = bt.sort_values(["customers", "trips"], ascending=False)
    bt = bt[["bus", "operator", "state", "main_route", "routes", "customers", "regular_customers", "regular_%", "trips",
             "trips_per_customer", "first_trip", "last_trip"]]

    k = st.columns(4)
    k[0].metric("Buses", f"{len(bt):,}")
    k[1].metric("Customers per bus (median)", f"{bt.customers.median():,.0f}")
    k[2].metric("Buses with 10+ regular customers", f"{int((bt.regular_customers >= 10).sum()):,}")
    k[3].metric("Trips with a known bus", f"{len(nb):,}", f"{100 * len(nb) / len(n):.0f}% of trips", delta_color="off",
                delta_arrow="off")
    top_n = st.slider("Buses to show", 10, 50, 25, key=f"{key}_bus_n")
    top = bt.head(top_n).iloc[::-1].copy()
    top["label"] = top.bus + "  ·  " + top.main_route.str.slice(0, 32)
    top["others"] = top.customers - top.regular_customers
    long = top.melt(id_vars=["label", "operator", "customers"], value_vars=["regular_customers", "others"],
                    var_name="kind", value_name="people")
    long["kind"] = long.kind.map({"regular_customers": f"Regular customers ({LOYAL}+ rides)", "others": "Other customers"})
    fig = px.bar(long, x="people", y="label", color="kind", orientation="h", custom_data=["operator", "customers"],
                 color_discrete_map={f"Regular customers ({LOYAL}+ rides)": BLUE, "Other customers": "#b8d3f5"},
                 category_orders={"kind": [f"Regular customers ({LOYAL}+ rides)", "Other customers"]})
    fig.update_traces(hovertemplate="%{y}<br>%{customdata[0]}<br>%{fullData.name}: %{x:,} of %{customdata[1]:,} customers"
                                    "<extra></extra>", marker_line_color="white", marker_line_width=1)
    st.plotly_chart(style(fig, 140 + 26 * len(top)).update_layout(
        title=f"The {len(top)} buses with the most customers (bus number · its main route)", barmode="stack",
        xaxis_title="Customers", yaxis_title=None), width="stretch")
    st.markdown("**Every bus**")
    st.dataframe(bt, width="stretch", hide_index=True)
    download(bt, f"{key}_buses", "Download bus table (CSV)")

    pick = st.selectbox("See the customers of one bus", bt.bus.tolist(), key=f"{key}_bus_pick",
                        format_func=lambda b: f"{b} — {int(bt.set_index('bus').customers[b]):,} customers")
    sel = nb[nb.bus == pick]
    one = sel.groupby("cid").agg(trips=("date", "size"), first_trip=("date", "min"), last_trip=("date", "max")).reset_index()
    one["usual_route"] = one.cid.map(mode_by(sel, "cid", "route"))
    one = one.assign(customer_id=anon(one.cid), first_trip=one.first_trip.dt.date, last_trip=one.last_trip.dt.date,
                     rider=np.where(one.trips >= LOYAL, "Regular", "Occasional"))
    one = one[["customer_id", "rider", "trips", "usual_route", "first_trip", "last_trip"]].sort_values("trips", ascending=False)
    st.dataframe(one, width="stretch", hide_index=True, height=min(420, 38 + 35 * len(one)))
    download(one, f"{key}_bus_{pick}_customers", f"Download customers of {pick} ({len(one):,}, anonymised)")


def customer_table(n, as_of, extra=None):
    per = n.groupby("cid").agg(total_trips=("date", "size"), months_active=("month", "nunique"),
                               first_trip=("date", "min"), last_trip=("date", "max"))
    per["home_state"] = mode_by(n, "cid", "state")
    per["usual_bus"] = mode_by(n, "cid", "bus", skip=NO_BUS).reindex(per.index).fillna("—")
    per["operator"] = mode_by(n, "cid", "operator")
    rc = n.groupby(["cid", "route"]).size().rename("t").reset_index().sort_values(["cid", "t"], ascending=[True, False])
    per = per.join(rc.groupby("cid").first().rename(columns={"route": "usual_route", "t": "trips_on_usual_route"}))
    per["routes_used"] = rc.groupby("cid").size()
    rc["rank"] = rc.groupby("cid").cumcount()
    top5 = rc[rc["rank"] < 5].assign(s=lambda d: d.route + " (" + d.t.astype(str) + ")").groupby("cid").s.agg(", ".join)
    more = per.routes_used - 5
    per["all_routes"] = top5 + np.where(more > 0, " + " + more.astype(str) + " more", "")
    per["days_since_last_trip"] = (as_of - per.last_trip).dt.days
    per["status"] = per.days_since_last_trip.map(status)
    per["rider_type"] = np.select([per.months_active >= 3, per.total_trips >= 2],
                                  ["Regular (3+ months)", "Repeat (2+ trips)"], "One-time")
    per["first_trip"] = per.first_trip.dt.date
    per["last_trip"] = per.last_trip.dt.date
    per = per.reset_index()
    if extra is not None:
        per = per.merge(extra, on="cid", how="left")
    per.insert(0, "customer_id", anon(per.cid))
    return per


def customers_header(note):
    st.subheader("Customer list — every passenger, their usual route and when they last travelled")
    explain("One row per passenger (anonymised ID — no phone numbers here). **Status** shows how recently they travelled; "
            "**rider type** shows how often. Use the filters to build a list (for example *lapsed regulars on one route*) "
            f"and download it. {note}")


def view_customers(per, key, cols):
    f1, f2, f3, f4 = st.columns([2, 2, 2.6, 1.2])
    s_sel = f1.multiselect("Status", [s for _, s in STATUS] + (["Never travelled"] if "Never travelled" in set(per.status)
                                                                else []), key=f"{key}_cu_status", placeholder="Any")
    t_sel = f2.multiselect("Rider type", per.rider_type.value_counts().index.tolist(), key=f"{key}_cu_type",
                           placeholder="Any")
    r_sel = f3.multiselect("Usual route", per.usual_route.dropna().value_counts().index.tolist(), key=f"{key}_cu_route",
                           placeholder="Any route")
    min_t = f4.number_input("Min trips", 0, 500, 0, key=f"{key}_cu_min")
    v = per
    if s_sel:
        v = v[v.status.isin(s_sel)]
    if t_sel:
        v = v[v.rider_type.isin(t_sel)]
    if r_sel:
        v = v[v.usual_route.isin(r_sel)]
    if min_t:
        v = v[v.total_trips.fillna(0) >= min_t]
    k = st.columns(4)
    k[0].metric("Customers in this list", f"{len(v):,}")
    k[1].metric("Regulars", f"{int((v.rider_type == 'Regular (3+ months)').sum()):,}")
    k[2].metric("Lapsed or dormant", f"{int(v.status.isin([STATUS[2][1], STATUS[3][1]]).sum()):,}")
    if "wallet_balance" in v:
        k[3].metric("Money left in their wallets", f"₹{v.wallet_balance.fillna(0).sum():,.0f}")
    else:
        k[3].metric("Trips by these customers", f"{int(v.total_trips.sum()):,}")
    v = v.sort_values(["total_trips", "last_trip"], ascending=False, na_position="last")
    st.dataframe(v[cols], width="stretch", hide_index=True, height=520)
    download(v[cols], f"{key}_customers", f"Download this list ({len(v):,} customers, anonymised)")

    st.markdown("**Who is in the list**")
    a, b = st.columns(2)
    sc = v.status.value_counts().reindex([s for _, s in STATUS] + ["Never travelled"]).dropna().rename("people").reset_index()
    fig = px.bar(sc, x="people", y=sc.columns[0], orientation="h", text="people")
    fig.update_traces(marker_color=BLUE, texttemplate="%{text:,}", textposition="outside", cliponaxis=False,
                      hovertemplate="%{y}: %{x:,} customers<extra></extra>")
    a.plotly_chart(style(fig, 300).update_layout(title="When did they last travel?", xaxis_title=None, yaxis_title=None,
                                                 yaxis=dict(autorange="reversed")), width="stretch")
    tc = v.rider_type.value_counts().rename("people").reset_index()
    fig = px.bar(tc, x="people", y=tc.columns[0], orientation="h", text="people")
    fig.update_traces(marker_color=BLUE, texttemplate="%{text:,}", textposition="outside", cliponaxis=False,
                      hovertemplate="%{y}: %{x:,} customers<extra></extra>")
    b.plotly_chart(style(fig, 300).update_layout(title="How often do they travel?", xaxis_title=None, yaxis_title=None),
                   width="stretch")


def view_return_rate(n, key, unit):
    st.subheader("Do new passengers come back? Return rate month by month")
    explain(f"Each **row** is a group of passengers whose **first {unit}** was in that month. Each **column** shows what share "
            f"of that group travelled again 1, 2, 3 … months later. Darker = more came back. M0 is the joining month "
            f"(always 100%, shown as text). Empty boxes are months that haven't finished yet. Pick a route to see whether "
            f"people return to **that same route**.")
    h1, h2, h3, h4 = st.columns([2.4, 1.2, 1.2, 1.3])
    routes = n.route.value_counts()
    c_route = h1.selectbox("Route", ["All routes"] + [r for r in routes.index if r not in (CD.NO_ROUTE, P.NO_TOWN)][:400],
                           key=f"{key}_coh_route")
    c_show = h2.radio("Show", ["%", "People"], horizontal=True, key=f"{key}_coh_show")
    c_h = h3.radio("Months", [6, 12], horizontal=True, key=f"{key}_coh_h")
    c_min = h4.number_input("Hide groups under", 0, 5000, 5 if c_route != "All routes" else 20, step=5,
                            key=f"{key}_coh_min_{c_route == 'All routes'}")
    src = n if c_route == "All routes" else n[n.route == c_route]
    size, ret = cohort(src)
    ks = [x for x in range(0, c_h + 1) if x in ret.columns]
    rr = ret.loc[size[size >= c_min].index, ks]
    if rr.empty:
        st.info("All groups are smaller than the minimum size — lower 'Hide groups under'.")
        return
    opts = list(rr.index)
    if len(opts) > 1:
        lo, hi = st.select_slider("Joining months to show", options=opts, value=(opts[0], opts[-1]), key=f"{key}_coh_rng",
                                  format_func=lambda p: p.strftime("%b %Y"))
        rr = rr.loc[lo:hi]
    sz = size.reindex(rr.index)
    people = (rr.values * sz.values[:, None] / 100).round()
    z = rr.values if c_show == "%" else people
    txt = [["" if pd.isna(x) else (f"{x:.0f}%" if c_show == "%" else f"{x:,.0f}") for x in row] for row in z]
    zr = rr.drop(columns=[0], errors="ignore")
    zmax = max(10, float(zr.max().max())) if c_show == "%" and zr.notna().any().any() else None
    fig = go.Figure(go.Heatmap(
        z=np.where(np.array(ks)[None, :] == 0, np.nan, z) if c_show == "%" else z, x=[f"M{x}" for x in ks],
        y=[f"{p.strftime('%b %Y')}  ·  {int(s):,} joined" for p, s in zip(rr.index, sz)],
        colorscale=SEQ, zmin=0, zmax=zmax, text=txt, texttemplate="%{text}", xgap=2, ygap=2,
        colorbar=dict(title="% came back" if c_show == "%" else "People"), customdata=np.dstack([rr.values, people]),
        hovertemplate="Joined: %{y}<br>%{x}: %{customdata[1]:,.0f} people (%{customdata[0]:.1f}%)<extra></extra>"))
    st.plotly_chart(style(fig, max(360, 30 * len(rr) + 130)).update_layout(
        title="Months after joining →", yaxis=dict(autorange="reversed"), xaxis=dict(side="top")), width="stretch")
    avg = []
    for x in ks[1:]:
        ok = rr[x].notna()
        if ok.any():
            avg.append((f"After {x} mo", float((rr[x][ok] * sz[ok]).sum() / sz[ok].sum())))
    if avg:
        av = pd.DataFrame(avg, columns=["when", "pct"])
        fig = px.bar(av, x="when", y="pct", text="pct")
        fig.update_traces(marker_color=BLUE, texttemplate="%{text:.1f}%", textposition="outside", cliponaxis=False,
                          hovertemplate="%{x}: %{y:.1f}% came back<extra></extra>")
        st.plotly_chart(style(fig, 300).update_layout(title="On average, how many came back (all groups together)",
                                                      xaxis_title=None, yaxis_title=None, yaxis=dict(ticksuffix="%")),
                        width="stretch")
    tbl = pd.DataFrame({"joined": [p.strftime("%b %Y") for p in rr.index], "people": sz.values}).join(
        rr.round(1).reset_index(drop=True).add_prefix("M"))
    download(tbl, f"{key}_return_rate", "Download return-rate table (CSV)")


# ---------------------------------------------------------------- sidebar: pick the passengers
CARD_VIEW, APP_VIEW = "Green Card passengers (tap on the bus)", "App & website bookings"
st.sidebar.title("Apnibus passengers")
st.sidebar.markdown("**1 · Which passengers?**")
view = st.sidebar.radio("Which passengers?", [CARD_VIEW, APP_VIEW], key="view", label_visibility="collapsed",
                        captions=["Paid by tapping a prepaid card on the conductor's machine · all states",
                                  "Booked online on our app or website · mostly Rajasthan"])
st.sidebar.divider()
st.sidebar.markdown("**2 · Narrow it down**")


def date_range(label, lo, hi, key):
    """Sidebar date range; while only one date is picked the filter waits for the second."""
    v = st.sidebar.date_input(label, (lo, hi), min_value=lo, max_value=hi, key=key)
    return (pd.Timestamp(v[0]), pd.Timestamp(v[1])) if isinstance(v, (tuple, list)) and len(v) == 2 else None


def reset_button(keys):
    if st.sidebar.button("Reset filters", width="stretch"):
        for x in keys:
            st.session_state.pop(x, None)
        st.rerun()


# ================================================================ A. Green Card passengers
if view == CARD_VIEW:
    st.title("Green Card passengers: who uses our card on the bus, on which routes, and who keeps coming back")
    with st.expander("What is this page? (start here if you are new)", expanded=False):
        st.markdown("""
Apnibus sells a **prepaid Green Card**. Passengers top it up with money and, instead of paying cash, **tap the card on the
conductor's ticket machine** when they board. The fare is taken from the card's wallet. Every tap is saved, and this page
turns those taps into answers:

* **State overview** — how many passengers use the card in each state, and how many come back.
* **Loyal routes** — routes where the same people travel again and again (daily commuters).
* **Buses & their riders** — how many customers each bus carries, and how many are regulars.
* **Customer list** — every passenger with their usual route, last trip and money left on the card — ready to download.
* **Return rate** — of the people who joined in a month, how many travelled again later.

*Source: apnibus-service-db → service_app_servicebooking (deleted rows and test users removed). Route names come from
ota_service: each is the bus's whole route (first → last town); the exact stop where a passenger got on or off is stored
in the conductor-machine system, not here.*
""")

    bst = CT.bus_state.value_counts().index.tolist()
    sel_bs = st.sidebar.multiselect("State (where the bus is registered)", bst, placeholder="All states", key="cd_state")
    cf = CT[CT.bus_state.isin(sel_bs)] if sel_bs else CT
    sel_op = st.sidebar.multiselect("Bus operator", cf.operator.value_counts().index.tolist(), placeholder="All operators",
                                    key="cd_op")
    if sel_op:
        cf = cf[cf.operator.isin(sel_op)]
    sel_rt = st.sidebar.multiselect("Route", [x for x in cf.route.value_counts().index if x != CD.NO_ROUTE],
                                    placeholder="All routes", key="cd_route")
    if sel_rt:
        cf = cf[cf.route.isin(sel_rt)]
    rng = date_range("Travel dates", CT.date.min().date(), CT.date.max().date(), "cd_dates")
    if rng:
        cf = cf[(cf.date >= rng[0]) & (cf.date <= rng[1])]
    reset_button(["cd_state", "cd_op", "cd_route", "cd_dates"])
    st.sidebar.caption(f"Showing **{len(cf):,}** of {len(CT):,} card trips.")

    if cf.empty:
        st.warning("No card trips match these filters — widen them in the sidebar.")
        st.stop()

    per = cf.groupby("customer_key").agg(trips=("booking_id", "size"), months=("month", "nunique"))
    k = st.columns(5)
    k[0].metric("Passengers", f"{len(per):,}", help="Different people (one per phone number / card) who tapped a card.")
    k[1].metric("Trips paid by card", f"{len(cf):,}")
    k[2].metric("Came back for a 2nd trip", f"{int((per.trips >= 2).sum()):,}", f"{100 * (per.trips >= 2).mean():.1f}%",
                delta_color="off", delta_arrow="off")
    k[3].metric("Regular riders", f"{int((per.months >= 3).sum()):,}", "travelled in 3+ different months",
                delta_color="off", delta_arrow="off")
    k[4].metric("Fares paid by card", f"₹{cf.paid_amount.sum():,.0f}")

    N = pd.DataFrame({"cid": cf.customer_key, "date": cf.date, "month": cf.month, "route": cf.route, "bus": cf.bus,
                      "operator": cf.operator, "state": cf.bus_state})
    NR = N[N.route != CD.NO_ROUTE]
    ctabs = st.tabs(["State overview", "Loyal routes", "Buses & their riders", "Customer list", "Return rate",
                     "How to read this"])

    with ctabs[0]:
        st.subheader("How many people use the Green Card in each state — and how many come back")
        sp = cf.groupby(["bus_state", "customer_key"]).agg(trips=("booking_id", "size"), months=("month", "nunique"))
        sb = sp.groupby(level=0).agg(passengers=("trips", "size"), trips=("trips", "sum"),
                                     came_back=("trips", lambda x: int((x >= 2).sum())),
                                     regular_riders=("months", lambda x: int((x >= 3).sum())))
        sb = sb.join(cf.groupby("bus_state").agg(routes=("route", lambda x: x[x != CD.NO_ROUTE].nunique()),
                                                 buses=("bus", "nunique"), fares_paid=("paid_amount", "sum"),
                                                 last_trip=("date", "max")))
        sb["came_back_%"] = (100 * sb.came_back / sb.passengers).round(1)
        sb["trips_per_passenger"] = (sb.trips / sb.passengers).round(2)
        sb["fares_paid"] = sb.fares_paid.astype(float).round(0)
        sb["last_trip"] = sb.last_trip.dt.date
        sb = sb.sort_values("trips", ascending=False).reset_index().rename(columns={"bus_state": "state"})
        main = sb.state.head(4).tolist()                                    # biggest states get their own colour
        STATE_COLORS = dict(zip(main, [BLUE, ORANGE, "#2e9e6b", "#8a5cd1"])) | {"Other states": "#a3a29b"}

        a, b = st.columns([1.15, 1])
        sbp = sb.head(10).iloc[::-1]
        fig = px.bar(sbp, x="passengers", y="state", orientation="h", text="passengers",
                     custom_data=["trips", "came_back_%", "regular_riders", "routes"])
        fig.update_traces(marker_color=BLUE, texttemplate="%{text:,}", textposition="outside", cliponaxis=False,
                          hovertemplate="%{y}<br>%{x:,} passengers · %{customdata[0]:,} trips<br>%{customdata[1]:.0f}% came "
                                        "back · %{customdata[2]:,} regulars · %{customdata[3]:,} routes<extra></extra>")
        a.plotly_chart(style(fig, 120 + 34 * len(sbp)).update_layout(title="Card passengers in each state",
                                                                     xaxis_title=None, yaxis_title=None), width="stretch")
        sbc = sb[sb.passengers >= 20].sort_values("came_back_%").reset_index(drop=True)
        fig = px.bar(sbc, x="came_back_%", y="state", orientation="h", text="came_back_%", custom_data=["passengers"])
        fig.update_traces(marker_color=ORANGE, texttemplate="%{text:.0f}%", textposition="outside", cliponaxis=False,
                          hovertemplate="%{y}: %{x:.1f}% of %{customdata[0]:,} passengers came back<extra></extra>")
        b.plotly_chart(style(fig, 120 + 34 * max(len(sbc), 1)).update_layout(
            title="Share who took a 2nd trip (states with 20+ passengers)", xaxis=dict(title=None, ticksuffix="%"),
            yaxis_title=None), width="stretch")

        ms = cf.assign(st_grp=np.where(cf.bus_state.isin(main), cf.bus_state, "Other states")) \
               .groupby(["month", "st_grp"]).customer_key.nunique().rename("people").reset_index()
        ms["month"] = ms.month.dt.to_timestamp()
        fig = px.line(ms, x="month", y="people", color="st_grp", markers=True, color_discrete_map=STATE_COLORS,
                      category_orders={"st_grp": main + ["Other states"]})
        fig.update_traces(line_width=2.5, hovertemplate="%{x|%b %Y}: %{y:,} passengers<extra>%{fullData.name}</extra>")
        st.plotly_chart(style(fig, 360).update_layout(title="Card passengers each month, by state — is usage growing or falling?",
                                                      xaxis_title=None, yaxis_title=None, hovermode="x unified"),
                        width="stretch")
        st.markdown("**State comparison**")
        st.dataframe(sb, width="stretch", hide_index=True)
        download(sb, "card_states", "Download state comparison (CSV)")
        st.divider()

        fm = cf.groupby("customer_key").month.min()
        mm = cf[["customer_key", "month"]].drop_duplicates()
        mm["who"] = np.where(mm.month == mm.customer_key.map(fm), "New passengers (first month)", "Returning passengers")
        mm = mm.groupby(["month", "who"]).size().rename("people").reset_index()
        mm["month"] = mm.month.dt.to_timestamp()
        fig = px.bar(mm, x="month", y="people", color="who",
                     color_discrete_map={"New passengers (first month)": BLUE, "Returning passengers": ORANGE},
                     category_orders={"who": ["New passengers (first month)", "Returning passengers"]})
        fig.update_traces(hovertemplate="%{x|%b %Y}: %{y:,} people<extra>%{fullData.name}</extra>",
                          marker_line_color="white", marker_line_width=1)
        st.plotly_chart(style(fig, 360).update_layout(title="Each month: new card passengers vs passengers coming back",
                                                      barmode="stack", xaxis_title=None, yaxis_title=None,
                                                      hovermode="x unified"), width="stretch")
        a, b = st.columns(2)
        allb = per.trips.map(band).value_counts().reindex([x[2] for x in TRIP_BANDS], fill_value=0).rename("people").reset_index()
        fig = px.bar(allb, x=allb.columns[0], y="people", text="people")
        fig.update_traces(marker_color=BLUE, texttemplate="%{text:,}", textposition="outside", cliponaxis=False,
                          hovertemplate="%{x}: %{y:,} passengers<extra></extra>")
        a.plotly_chart(style(fig, 340).update_layout(title="How many trips each passenger has taken",
                                                     xaxis_title=None, yaxis_title=None), width="stretch")
        ops = cf.groupby("operator").agg(trips=("booking_id", "size"), people=("customer_key", "nunique")) \
                .sort_values("trips", ascending=False).head(10).iloc[::-1].reset_index()
        fig = px.bar(ops, x="trips", y="operator", orientation="h", text="trips", custom_data=["people"])
        fig.update_traces(marker_color=BLUE, texttemplate="%{text:,}", textposition="outside", cliponaxis=False,
                          hovertemplate="%{y}<br>%{x:,} trips · %{customdata[0]:,} passengers<extra></extra>")
        b.plotly_chart(style(fig, 340).update_layout(title="Bus operators with the most card trips", xaxis_title=None,
                                                     yaxis_title=None), width="stretch")

    with ctabs[1]:
        view_loyal_routes(NR, "cd", f"{len(NR):,} of {len(N):,} card trips have a named route.")

    with ctabs[2]:
        view_buses(N, "cd", "Every card trip records the bus number.")

    with ctabs[3]:
        prof = CU.rename(columns={"customer_key": "cid"})[["cid", "language", "wallet_balance", "signed_up",
                                                           "last_recharge"]]
        prof["language"] = prof.language.map({"en": "English", "hi": "Hindi", "pa": "Punjabi", "gu": "Gujarati"}) \
                                        .fillna(prof.language)
        customers_header("**Wallet balance** = money still on the passenger's card — a strong reason for them to come back.")
        per_c = customer_table(N, CT.date.max(), prof)
        no_filter = not (sel_bs or sel_op or sel_rt or rng and (rng[0].date() > CT.date.min().date()
                                                                or rng[1].date() < CT.date.max().date()))
        add_never = st.toggle("Also list card holders who registered but never travelled", value=False, key="cd_cu_never",
                              disabled=not no_filter,
                              help="They have no trips, so they can't be filtered by state, route or date. "
                                   "Clear the sidebar filters to include them.")
        if add_never and no_filter:
            nv = prof[~prof.cid.isin(per_c.cid)].copy()
            nv.insert(0, "customer_id", anon(nv.cid))
            nv["status"], nv["rider_type"], nv["total_trips"] = "Never travelled", "Never travelled", 0
            per_c = pd.concat([per_c, nv], ignore_index=True)
        cols = ["customer_id", "status", "rider_type", "home_state", "usual_route", "trips_on_usual_route", "total_trips",
                "routes_used", "all_routes", "usual_bus", "operator", "first_trip", "last_trip", "days_since_last_trip",
                "months_active", "wallet_balance", "language", "signed_up", "last_recharge"]
        view_customers(per_c, "cd", cols)

    with ctabs[4]:
        view_return_rate(N, "cd", "card trip")

    with ctabs[5]:
        st.markdown(f"""
| Term | What it means |
|---|---|
| **Green Card trip** | One tap of the prepaid card on the conductor's machine (one row of `service_app_servicebooking`). Deleted rows and test users removed. |
| **Passenger / customer** | One person, identified by the phone number on their card account (or the card's chip id if no account). Shown only as an anonymised `C…` id. |
| **State** | Taken from the bus number plate (HP… = Himachal Pradesh, RJ… = Rajasthan). The card data has no state column. |
| **Route** | The bus's whole route, first → last town, from `ota_service`. The passenger's own boarding/drop stop is in the conductor-machine system, not in this database. |
| **Came back** | Took 2 or more card trips. **Regular rider** = travelled in 3+ different months. |
| **Loyal rider (route)** | Took the same route {LOYAL}+ times. **Regular customer (bus)** = rode the same bus {LOYAL}+ times. |
| **Status** | Days since the last trip: Active ≤ 30 · Slipping 31–90 · Lapsed 91–365 · Dormant > 365. *Never travelled* = registered a card but no trip yet. |
| **Wallet balance** | Money left on the card account (`user_wallet.balance`). |
| **Return rate** | Passengers grouped by the month of their first trip; M1, M2 … = share who travelled again that many months later. |
""")
    st.stop()

# ================================================================ B. App & website bookings
st.title("App & website bookings: where our passengers travel, on which buses, and who comes back")
with st.expander("What is this page? (start here if you are new)", expanded=False):
    st.markdown(f"""
These are bus tickets that passengers **booked themselves on the Apnibus app or website** for our own buses, and paid for
online. Some used the **Green Card pass** on the booking for a discount. This page shows:

* **Overview** — how many passengers and trips, month by month, and how they booked (app, website, Green Card pass).
* **Where people travel** — the busiest town-to-town routes and a from/to map of towns.
* **Loyal routes** — routes where the same people travel again and again.
* **Buses & their riders** — how many customers each bus carries (bus number is recorded for recent bookings only).
* **Customer list** — every passenger with their usual route and last trip — ready to download.
* **Return rate** — of the people who joined in a month, how many travelled again later.

*Source: ab_commuter → ticket_ticketnew where source = 1 (our buses) and is_paid = true; cancelled, deleted and test
tickets removed. A trip = one person, one day, one route (duplicate tickets merged). Trips counted up to
{M.AS_OF.date()}. These bookings are almost all in Rajasthan — Himachal, Punjab and Bihar travel is on the Green Card
riders page.*
""")

rng = date_range("Travel dates", J.journey_date.min().date(), J.journey_date.max().date(), "ap_dates")
states = [s for s in pd.concat([J.from_state, J.to_state]).value_counts().index if s not in (M.UNMAPPED, P.NO_TOWN)]
sel_states = st.sidebar.multiselect("State (trip starts or ends here)", states, placeholder="All states", key="ap_state")
gc_opt = st.sidebar.selectbox("Green Card pass", ["All trips", "Green Card only", "Without Green Card"], key="ap_gc")
sel_via = st.sidebar.multiselect("Booked through", J.booked_via.value_counts().index.tolist(), placeholder="App, website …",
                                 key="ap_via", help="ticket_sourcing: 1 = Website, 2 = App. '+ Green Card' = the Green Card "
                                                    "pass was used on that booking.")

f = J
if sel_via:
    f = f[f.booked_via.isin(sel_via)]
if rng:
    f = f[(f.journey_date >= rng[0]) & (f.journey_date <= rng[1])]
if sel_states:
    f = f[f.from_state.isin(sel_states) | f.to_state.isin(sel_states)]
if gc_opt == "Green Card only":
    f = f[f.service == M.GC]
elif gc_opt == "Without Green Card":
    f = f[f.service == M.LR]
towns = pd.concat([f.from_town, f.to_town]).value_counts()          # only towns left after the filters above
sel_towns = st.sidebar.multiselect("Town (trip starts or ends here)", [x for x in towns.index if x != P.NO_TOWN],
                                   placeholder="All towns", key="ap_town")
if sel_towns:
    f = f[f.from_town.isin(sel_towns) | f.to_town.isin(sel_towns)]
reset_button(["ap_dates", "ap_state", "ap_gc", "ap_via", "ap_town"])
c = f[f.completed]
st.sidebar.caption(f"Showing **{len(c):,}** of {int(J.completed.sum()):,} completed trips.")
if c.empty:
    st.warning("No completed trips match these filters — widen them in the sidebar.")
    st.stop()
ct = c[c.town_route != P.NO_TOWN]                    # trips with a known town pair

per = c.groupby("customer_key").size()
k = st.columns(5)
k[0].metric("Passengers", f"{len(per):,}", help="Different people (one per phone number) with a completed paid trip.")
k[1].metric("Trips", f"{len(c):,}")
k[2].metric("Came back for a 2nd trip", f"{int((per >= 2).sum()):,}", f"{100 * (per >= 2).mean():.1f}%", delta_color="off",
            delta_arrow="off")
k[3].metric("Trips with both towns known", f"{len(ct):,}", f"{100 * len(ct) / len(c):.0f}% of trips", delta_color="off",
            delta_arrow="off")
k[4].metric("Passengers who used the Green Card pass", f"{c[c.service == M.GC].customer_key.nunique():,}")

st_any = np.where(c.from_state.isin([P.NO_TOWN, M.UNMAPPED]), c.to_state, c.from_state)
NA = pd.DataFrame({"cid": c.customer_key, "date": c.journey_date, "month": c.month, "route": c.town_route, "bus": c.bus,
                   "operator": c.operator, "state": st_any})
NAR = NA[NA.route != P.NO_TOWN]
tabs = st.tabs(["Overview", "Where people travel", "Loyal routes", "Buses & their riders", "Customer list", "Return rate",
                "How to read this"])

with tabs[0]:
    st.subheader("Trips every month — and how many used the Green Card pass")
    m = c.groupby(["month", "service"]).size().rename("trips").reset_index()
    m["month"] = m.month.dt.to_timestamp()
    fig = px.bar(m, x="month", y="trips", color="service", color_discrete_map=SVC_COLORS,
                 category_orders={"service": [M.LR, M.GC]})
    fig.update_traces(hovertemplate="%{x|%b %Y}: %{y:,} trips<extra>%{fullData.name}</extra>",
                      marker_line_color="white", marker_line_width=1)
    st.plotly_chart(style(fig, 340).update_layout(title="Paid trips per month", barmode="stack", xaxis_title=None,
                                                  yaxis_title=None, hovermode="x unified"), width="stretch")

    st.divider()
    st.subheader("How did passengers book — app, website or with the Green Card pass?")
    via_order = [v for v in VIA_COLORS if v in set(c.booked_via)] + sorted(set(c.booked_via) - set(VIA_COLORS))
    vt = c.groupby("booked_via").agg(trips=("customer_key", "size"), people=("customer_key", "nunique"))
    vk = st.columns(len(via_order[:4]))
    for col, v in zip(vk, via_order[:4]):
        col.metric(v, f"{int(vt.trips.get(v, 0)):,} trips", f"{100 * vt.trips.get(v, 0) / len(c):.1f}% · "
                   f"{int(vt.people.get(v, 0)):,} people", delta_color="off", delta_arrow="off")

    sv = pd.concat([c.assign(state=c.from_state), c.assign(state=c.to_state)])
    sv = sv[sv.state != M.UNMAPPED].drop_duplicates(["journey_key", "state"])      # a trip counts once per state it touches
    top_st = sv.state.value_counts().head(8).index.tolist()
    sv = sv[sv.state.isin(top_st)].groupby(["state", "booked_via"]).size().rename("trips").reset_index()
    sv["pct"] = 100 * sv.trips / sv.groupby("state").trips.transform("sum")
    st_lab = {s: f"{s}  ·  {n:,} trips" for s, n in sv.groupby("state").trips.sum().items()}
    sv["state_lab"] = sv.state.map(st_lab)
    fig = px.bar(sv, x="pct", y="state_lab", color="booked_via", orientation="h", custom_data=["trips"],
                 color_discrete_map=VIA_COLORS, category_orders={"booked_via": via_order,
                                                                 "state_lab": [st_lab[s] for s in top_st]})
    fig.update_traces(hovertemplate="%{y}<br>%{fullData.name}: %{customdata[0]:,} trips (%{x:.1f}%)<extra></extra>",
                      marker_line_color="white", marker_line_width=1)
    st.plotly_chart(style(fig, 140 + 40 * len(top_st)).update_layout(
        title="Booking channel in each state (trip starts or ends there)", barmode="stack",
        xaxis=dict(title=None, ticksuffix="%", range=[0, 100]), yaxis_title=None), width="stretch")

    ve = c.groupby(["era", "booked_via"]).size().unstack(fill_value=0).reindex(columns=via_order, fill_value=0)
    ve["total"] = ve.sum(axis=1)
    st.markdown("**Booking channel by period**")
    st.dataframe(ve.reset_index(), width="content", hide_index=True)
    st.caption("Only tickets from **2024 onwards** record the channel reliably. Older migrated tickets (2021–24) are all "
               "marked App — most likely a default filled in during migration, not the real channel. Green Card here = "
               "the pass used on an app/website booking; card taps on the bus are on the Green Card passengers page.")
    st.divider()
    era = (c.groupby("era").agg(trips=("customer_key", "size"), people=("customer_key", "nunique"),
                                with_towns=("town_route", lambda s: int((s != P.NO_TOWN).sum())),
                                first=("journey_date", "min"), last=("journey_date", "max")).reset_index())
    era["first"] = era["first"].dt.date; era["last"] = era["last"].dt.date
    st.markdown("**Which periods have town information**")
    st.dataframe(era.sort_values("first"), width="content", hide_index=True)
    st.caption("2022–24 towns are recovered from the old ticket_ticket table (same PNR and same customer). "
               "The first tickets (Dec-2021 → May-2022) have no town at all; they count in the totals and the return rate "
               "but not in the route views.")

with tabs[1]:
    st.subheader("Where do people travel? The busiest town-to-town routes")
    explain("Each route is **from town → to town** as booked (A → B and B → A are separate). Use the grid to see, for "
            "each starting town (rows), where its passengers go (columns).")
    if ct.empty:
        st.info("No trips with known towns for these filters.")
    else:
        rt = route_stats(f, "town")
        g1, g2, g3 = st.columns([1.6, 2.6, 1.4])
        order = g1.selectbox("Rank routes by", ["unique_customers", "completed_journeys", "repeat_customers",
                                                "route_regular_customers", "repeat_customer_pct"],
                             format_func={"unique_customers": "Passengers", "completed_journeys": "Trips",
                                          "repeat_customers": "Passengers who came back (2+)",
                                          "route_regular_customers": f"Loyal riders ({LOYAL}+ trips)",
                                          "repeat_customer_pct": "% who came back"}.get, key="ap_tt_order")
        cell = g2.radio("Grid shows", ["unique_customers", "repeat_customer_pct", "regular_customers"], horizontal=True,
                        format_func={"unique_customers": "Passengers", "repeat_customer_pct": "% who came back",
                                     "regular_customers": f"Loyal riders ({LOYAL}+)"}.get, key="ap_tt_cell")
        n_top = g3.slider("Towns in grid", 8, 30, 15, key="ap_tt_n")
        min_p = 20 if order == "repeat_customer_pct" else 1
        rk = rt[rt.unique_customers >= min_p].sort_values(order, ascending=False)
        top = rk.head(20).iloc[::-1]
        fig = px.bar(top, x=order, y="route", orientation="h", text=order,
                     custom_data=["unique_customers", "completed_journeys", "repeat_customer_pct", "route_regular_customers"])
        fig.update_traces(marker_color=BLUE, textposition="outside", cliponaxis=False,
                          texttemplate="%{text:.0f}%" if order == "repeat_customer_pct" else "%{text:,}",
                          hovertemplate="%{y}<br>%{customdata[0]:,} passengers · %{customdata[1]:,} trips<br>"
                                        "%{customdata[2]:.0f}% came back · %{customdata[3]:,} loyal riders<extra></extra>")
        st.plotly_chart(style(fig, 600).update_layout(
            title="The 20 busiest town-to-town routes" + (" (routes with 20+ passengers)" if min_p > 1 else ""),
            xaxis_title=None, yaxis_title=None), width="stretch")

        mx = town_matrix(f)
        mx = mx[(mx.origin_town != P.NO_TOWN) & (mx.destination_town != P.NO_TOWN)]
        topo = mx.groupby("origin_town").unique_customers.sum().nlargest(n_top).index
        topd = mx.groupby("destination_town").unique_customers.sum().nlargest(n_top).index
        sub = mx[mx.origin_town.isin(topo) & mx.destination_town.isin(topd)]
        pv = sub.pivot(index="origin_town", columns="destination_town", values=cell).reindex(index=topo, columns=topd)
        pc = sub.pivot(index="origin_town", columns="destination_town", values="unique_customers").reindex(index=topo, columns=topd)
        pj = sub.pivot(index="origin_town", columns="destination_town", values="journeys").reindex(index=topo, columns=topd)
        fig = go.Figure(go.Heatmap(
            z=pv.values, x=pv.columns, y=pv.index, colorscale=SEQ, customdata=np.dstack([pc.values, pj.values]),
            text=[["" if pd.isna(v) else (f"{v:.0f}%" if cell == "repeat_customer_pct" else f"{v:,.0f}") for v in row]
                  for row in pv.values], texttemplate="%{text}", xgap=2, ygap=2,
            colorbar=dict(title={"unique_customers": "Passengers", "repeat_customer_pct": "% came back",
                                 "regular_customers": "Loyal"}[cell]),
            hovertemplate="From %{y} → to %{x}<br>%{customdata[0]:,} passengers · %{customdata[1]:,} trips<br>"
                          "value: %{z:,.1f}<extra></extra>"))
        st.plotly_chart(style(fig, 260 + 26 * n_top).update_layout(
            title=f"From which town (rows) to which town (columns) — the {n_top} busiest of each",
            yaxis=dict(autorange="reversed", title="From"), xaxis=dict(tickangle=-40, title="To")), width="stretch")
        st.caption("Empty box = nobody made that trip.")
        with st.expander("All routes (table)"):
            st.dataframe(rk.drop(columns=["long_route_journeys"]).rename(columns={"green_card_journeys": "green_card_trips"}),
                         width="stretch", hide_index=True)
        download(rk, "town_routes", "Download route table (CSV)")

with tabs[2]:
    view_loyal_routes(NAR, "ap", f"{len(NAR):,} of {len(NA):,} trips have both towns known (bookings from Dec-2021 → "
                                 f"May-2022 have no towns).")

with tabs[3]:
    view_buses(NA, "ap", "The bus number is recorded only for recent bookings (about 1 in 10 trips), so these counts "
                         "cover those trips only.")

with tabs[4]:
    customers_header("Trips from Dec-2021 → May-2022 have no towns, so some passengers show *Town not recorded* as "
                     "their route.")
    per_a = customer_table(NA, M.AS_OF)
    per_a.loc[per_a.usual_route == P.NO_TOWN, "usual_route"] = "Town not recorded"
    cols = ["customer_id", "status", "rider_type", "home_state", "usual_route", "trips_on_usual_route", "total_trips",
            "routes_used", "all_routes", "usual_bus", "first_trip", "last_trip", "days_since_last_trip", "months_active"]
    view_customers(per_a, "ap", cols)

with tabs[5]:
    view_return_rate(NA, "ap", "trip")

with tabs[6]:
    st.markdown(f"""
| Term | What it means |
|---|---|
| **Booking** | `ticket_ticketnew` where `source = 1` (our buses) and `is_paid = true`. Cancelled, deleted and test tickets removed. |
| **Trip** | One person + one travel date + one route + one bus service. Duplicate tickets for the same trip are merged. |
| **Passenger / customer** | One phone number, shown only as an anonymised `C…` id. |
| **Green Card pass** | The booking carries the Green Card `pass_id` (`pass_reward_id`, always b1f1ae25…) or `ticket_with_pass = true`. |
| **Booked through** | `ticket_sourcing`: 1 = Website, 2 = App, 3 = Agent. Reliable only from 2024; older migrated tickets all show App. |
| **Towns / route** | From the ticket; for 2022–24 migrated tickets from the old `ticket_ticket` table (same PNR **and** same customer). Dec-2021 → May-2022 tickets have no towns. |
| **Bus** | Bus number from the bus service on the ticket — recorded for recent bookings only (about 1 in 10 trips). |
| **Came back** | 2+ trips. **Regular** = travelled in 3+ different months. **Loyal rider (route)** = same route {LOYAL}+ times; **regular customer (bus)** = same bus {LOYAL}+ times. |
| **Status** | Days since the last trip (up to {M.AS_OF.date()}): Active ≤ 30 · Slipping 31–90 · Lapsed 91–365 · Dormant > 365. |
| **Return rate** | Passengers grouped by the month of their first trip; M1, M2 … = share who travelled again that many months later. |
""")
