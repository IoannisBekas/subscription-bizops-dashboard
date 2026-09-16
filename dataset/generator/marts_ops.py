"""Product usage & compute cost, GPU clusters, and ticket-level customer support."""
import numpy as np
import pandas as pd
from config import NM, COUNTRIES, FEATURES, TOKEN_PACKS, interp
from marts_core import CODES

DAY_W = np.array([0.97, 0.96, 0.97, 0.98, 1.02, 1.06, 1.05])
FID = FEATURES.feature_id.tolist()
TOK_PER_UNIT = dict(zip(FID, FEATURES.tokens_per_unit))
ADOPTION = {"F01": 0.97, "F02": 0.35, "F03": 0.06, "F04": 0.30, "F05": 0.13, "F06": 0.02, "F07": 0.03, "F08": 0.05}
CONTENT_COST = {"F07": 0.20, "F08": 0.40}
BASE_P95 = {"F01": 1800, "F02": 2600, "F03": 900, "F04": 9000, "F05": 95000, "F06": 14000, "F07": 400, "F08": 700}
CLUSTERS = pd.DataFrame([
    ("GC1", "Cloud A", "H100 80GB", "On-demand", 3.20, "2024-01-01", ""),
    ("GC2", "Cloud A", "A100 80GB", "1-yr reserved", 1.35, "2024-01-01", "2025-12-31"),
    ("GC3", "Cloud B", "L40S 48GB", "Spot", 0.75, "2024-06-01", ""),
    ("GC4", "Cloud B", "H200 141GB", "On-demand", 3.80, "2025-06-01", ""),
    ("GC5", "Cloud C", "H100 80GB", "1-yr reserved", 2.05, "2026-02-01", ""),
], columns=["cluster_id", "provider", "gpu_type", "pricing_model", "hourly_rate_usd", "live_from", "retired_on"])
ALLOC = [  # from date: {workload: {cluster: share}}
    ("2024-01-01", {"LLM chat": {"GC2": .6, "GC1": .4}, "Speech": {"GC1": 1}, "Image": {"GC1": .5, "GC2": .5}, "Video": {"GC1": 1}}),
    ("2024-06-01", {"LLM chat": {"GC2": .55, "GC1": .45}, "Speech": {"GC3": .7, "GC1": .3}, "Image": {"GC3": .6, "GC1": .4}, "Video": {"GC1": 1}}),
    ("2025-06-01", {"LLM chat": {"GC2": .5, "GC1": .5}, "Speech": {"GC3": .8, "GC1": .2}, "Image": {"GC3": .7, "GC1": .3}, "Video": {"GC4": .7, "GC1": .3}}),
    ("2026-01-01", {"LLM chat": {"GC1": 1}, "Speech": {"GC3": .8, "GC1": .2}, "Image": {"GC3": .7, "GC1": .3}, "Video": {"GC4": .7, "GC1": .3}}),
    ("2026-02-01", {"LLM chat": {"GC5": .8, "GC1": .2}, "Speech": {"GC3": .8, "GC5": .2}, "Image": {"GC3": .6, "GC5": .4}, "Video": {"GC5": .5, "GC4": .4, "GC1": .1}}),
]


def step(days, v0, changes):
    v = np.full(len(days), v0, float)
    for d, val in changes:
        v[days >= np.datetime64(d)] = val
    return v


def fact_usage_daily(dd, bridge, funnel, tx, rng):
    days = dd[dd.is_actual].date.to_numpy().astype("datetime64[D]")
    di = pd.DatetimeIndex(days)
    m = ((di.year - 2024) * 12 + di.month - 1).to_numpy()
    wd = DAY_W[di.weekday]
    b = bridge.groupby("t")[["subs_start", "subs_end"]].sum()
    prem = ((b.subs_start + b.subs_end) / 2).to_numpy()
    prem_dau = prem[m] * np.where(days >= np.datetime64("2025-07-15"), 0.50, 0.46) * wd * np.exp(rng.normal(0, 0.03, len(days)))
    su = funnel.groupby("date").free_signups.sum().reindex(di.date, fill_value=0)
    pre = su.iloc[:31].mean() * np.linspace(0.45, 0.95, 180)          # H2-2023 sign-ups (site live before 2024)
    full = pd.Series(np.r_[pre, su.to_numpy()])
    r30 = full.rolling(30).sum().to_numpy()[180:]
    r180 = full.rolling(180).sum().to_numpy()[180:]
    free_dau = (0.30 * r30 + 0.03 * (r180 - r30)) * wd * np.exp(rng.normal(0, 0.03, len(days)))
    bought = tx[tx.type == 3].assign(tk=lambda d: TOKEN_PACKS.tokens.to_numpy()[d.item]).groupby("t").tk.sum().reindex(range(NM), fill_value=0)
    tok_m = prem * 100 * 0.72 + bought.to_numpy() * 0.93
    wsum = pd.Series(wd).groupby(m).transform("sum").to_numpy()
    tok_day = tok_m[m] * wd / wsum
    launch = {f: np.datetime64(d) for f, d in zip(FID, FEATURES.launch_date)}
    video_ramp = np.clip((days - launch["F05"]).astype(int) / 60, 0, 1)
    raw = {"F02": np.full(len(days), 0.05), "F03": np.full(len(days), 0.08),
           "F04": np.where(days >= launch["F05"], 0.40, 0.50), "F05": 0.10 + 0.16 * video_ramp,
           "F06": np.where(days >= np.datetime64("2025-01-01"), 0.03, 0.05), "F07": np.full(len(days), 0.07),
           "F08": np.full(len(days), 0.07)}
    for f in raw:
        raw[f] = np.where(days >= launch[f], raw[f], 0)
    tot = sum(raw.values())
    cost = {
        "F01": step(days, 0.0011, [("2025-06-02", 0.00092), ("2025-11-17", 0.00072), ("2026-02-02", 0.00065)]),
        "F02": step(days, 0.0030, [("2025-06-02", 0.0024), ("2026-02-02", 0.0019)]),
        "F03": step(days, 0.018, [("2025-06-02", 0.015), ("2026-02-02", 0.012)]),
        "F04": step(days, 0.0065, [("2025-05-05", 0.0052), ("2026-02-02", 0.0042)]),
        "F05": step(days, 0.22, [("2025-04-07", 0.16), ("2025-11-17", 0.11), ("2026-02-02", 0.095)]),
        "F06": step(days, 0.012, [("2026-02-02", 0.010)]), "F07": np.zeros(len(days)), "F08": np.zeros(len(days))}
    crunch = (days >= np.datetime64("2024-11-04")) & (days <= np.datetime64("2024-12-15"))
    promo = dd[dd.is_actual].promo_event.ne("").to_numpy()
    opt = np.clip((days - np.datetime64("2025-06-01")).astype(int) / 300, 0, 1)
    frames = []
    msgs_prem = interp({0: 40, 31: 46})[m]
    msgs_free = np.where(days >= np.datetime64("2025-11-10"), 11.0, 16.0)
    for f in FID:
        for utype in ("Premium", "Free"):
            if utype == "Free" and f != "F01":
                continue
            dau = prem_dau if utype == "Premium" else free_dau
            if f == "F01":
                units = dau * (msgs_prem if utype == "Premium" else msgs_free)
                tokens = np.zeros(len(days))
            else:
                tokens = tok_day * raw[f] / tot
                units = tokens / TOK_PER_UNIT[f]
            live = days >= launch[f]
            users = np.where(live, dau * ADOPTION[f] * np.exp(rng.normal(0, 0.04, len(days))), 0)
            p95 = BASE_P95[f] * (1 - 0.30 * opt) * np.where(promo, 1.15, 1.0) * np.exp(rng.normal(0, 0.05, len(days)))
            p95 *= np.where(crunch & np.isin(f, ["F04", "F05"]), 1.9, 1.0)
            err = 0.004 * np.exp(rng.normal(0, 0.25, len(days))) + np.where(crunch & (f == "F05"), 0.05, 0) + np.where(crunch & (f == "F04"), 0.015, 0)
            cache = np.where(f == "F01", np.clip((days - np.datetime64("2025-11-17")).astype(int) / 90, 0, 1) * 0.35, 0)
            frames.append(pd.DataFrame({
                "date": di.date, "feature_id": f, "user_type": utype, "active_users": np.round(users).astype(int),
                "units": np.round(np.where(live, units, 0)).astype(int), "tokens_consumed": np.round(np.where(live, tokens, 0)).astype(int),
                "compute_cost_usd": np.where(live, units * cost[f], 0).round(2),
                "content_cost_usd": np.where(live, units * CONTENT_COST.get(f, 0), 0).round(2),
                "p95_latency_ms": np.where(live, p95, np.nan).round(0), "error_rate": np.where(live, err, np.nan).round(4),
                "cache_hit_rate": np.where(live, cache + np.where(cache > 0, rng.normal(0, 0.01, len(days)), 0), np.nan).round(3)}))
    u = pd.concat(frames, ignore_index=True)
    return u[u.units > 0].reset_index(drop=True)


def fact_gpu_daily(usage, rng):
    wl = {"F01": [("LLM chat", 1.0)], "F02": [("Speech", 1.0)], "F03": [("Speech", 1.0)], "F04": [("Image", 1.0)],
          "F05": [("Video", 1.0)], "F06": [("LLM chat", 0.3), ("Image", 0.7)]}
    parts = []
    for f, splits in wl.items():
        g = usage[usage.feature_id == f].groupby("date")[["compute_cost_usd", "units"]].sum()
        for w, sh in splits:
            parts.append(pd.DataFrame({"date": g.index, "workload": w, "cost": g.compute_cost_usd.to_numpy() * sh,
                                       "units": g.units.to_numpy() * sh}))
    wd = pd.concat(parts).groupby(["date", "workload"], as_index=False).sum()
    rate = CLUSTERS.set_index("cluster_id").hourly_rate_usd
    rows = []
    dts = pd.to_datetime(wd.date).to_numpy()
    for i, (start, alloc) in enumerate(ALLOC):
        end = np.datetime64(ALLOC[i + 1][0]) if i + 1 < len(ALLOC) else np.datetime64("2100-01-01")
        sel = wd[(dts >= np.datetime64(start)) & (dts < end)]
        for w, shares in alloc.items():
            x = sel[sel.workload == w]
            for cl, sh in shares.items():
                util = {"GC2": 0.68, "GC5": 0.76, "GC3": 0.83}.get(cl, 0.88)
                rows.append(pd.DataFrame({"date": x.date, "cluster_id": cl, "workload": w, "cost_usd": (x.cost * sh).round(2),
                                          "units_served": np.round(x.units * sh).astype(int),
                                          "gpu_hours": (x.cost * sh / rate[cl]).round(1),
                                          "avg_utilization": np.clip(util + rng.normal(0, 0.03, len(x)), 0.4, 0.97).round(3)}))
    return pd.concat(rows, ignore_index=True).sort_values(["date", "cluster_id", "workload"]).reset_index(drop=True)


CATS = pd.DataFrame([  # category, base weight, team, median resolution hours
    ("Billing & payments", 0.20, "Billing specialists", 10), ("Refund request", 0.06, "Billing specialists", 20),
    ("Cancellation help", 0.12, "Tier 1 (BPO)", 6), ("Tokens & purchases", 0.11, "Billing specialists", 12),
    ("Content moderation / flagged chat", 0.10, "Trust & Safety", 30), ("Account & login", 0.10, "Tier 1 (BPO)", 12),
    ("Technical - image / video", 0.10, "Engineering escalation", 40), ("Technical - chat / voice", 0.07, "Engineering escalation", 30),
    ("Age verification (UK)", 0.00, "Trust & Safety", 8), ("Feature request / feedback", 0.04, "Tier 1 (BPO)", 20),
], columns=["category", "w", "team", "res_h"])
RESOLUTIONS = {
    "Billing & payments": ["Resolved - billing explained", "Payment method updated"], "Refund request": ["Refund denied"],
    "Cancellation help": ["Cancelled for user"], "Tokens & purchases": ["Tokens credited", "Resolved - guidance"],
    "Content moderation / flagged chat": ["Content reviewed - no action", "Content reviewed - warning upheld"],
    "Account & login": ["Account restored", "Resolved - guidance"], "Technical - image / video": ["Bug fixed", "Workaround provided"],
    "Technical - chat / voice": ["Bug fixed", "Workaround provided"], "Age verification (UK)": ["Verification completed", "Verification failed"],
    "Feature request / feedback": ["Logged for product"],
}
HOUR_W = np.array([5, 4, 3, 2, 2, 2, 2, 3, 4, 5, 5, 5, 5, 5, 6, 6, 6, 7, 8, 9, 10, 10, 9, 7], float)


def fact_support_tickets(dd, s, tx, active_idx, usage, rng):
    days = dd[dd.is_actual].date.to_numpy().astype("datetime64[D]")
    di = pd.DatetimeIndex(days)
    m = ((di.year - 2024) * 12 + di.month - 1).to_numpy()
    prem = np.array([len(a) for a in active_idx])[m].astype(float)
    free = usage[(usage.feature_id == "F01") & (usage.user_type == "Free")].set_index("date").active_users.reindex(di.date, fill_value=0).to_numpy()
    promo = dd[dd.is_actual].promo_event.ne("").to_numpy()
    wdm = np.where(di.weekday == 0, 1.15, np.where(di.weekday >= 5, 0.85, 1.0)) * np.where(promo, 1.2, 1.0)
    lam_p, lam_f = prem * 0.00135 * wdm, free * 0.00006 * wdm
    n_p, n_f = rng.poisson(lam_p), rng.poisson(lam_f)
    day_i = np.r_[np.repeat(np.arange(len(days)), n_p), np.repeat(np.arange(len(days)), n_f)]
    is_prem = np.r_[np.ones(n_p.sum(), bool), np.zeros(n_f.sum(), bool)]
    N = len(day_i)
    d = days[day_i]
    sid = np.full(N, -1)
    for t in range(NM):
        sel = np.nonzero(is_prem & (m[day_i] == t))[0]
        sid[sel] = rng.choice(active_idx[t], len(sel))
    cw = COUNTRIES._w26.to_numpy() / COUNTRIES._w26.sum()
    ctry = np.where(sid >= 0, s.country.to_numpy()[np.clip(sid, 0, None)], rng.choice(len(cw), N, p=cw))
    # category mix shifts
    W = np.tile(CATS.w.to_numpy(), (N, 1))
    W[:, 2] = np.where(d >= np.datetime64("2025-04-14"), 0.04, 0.12)                          # self-serve cancel
    crunch = (d >= np.datetime64("2024-11-04")) & (d <= np.datetime64("2024-12-15"))
    W[:, 6] *= np.where(crunch, 2.5, 1.0)
    W[:, 0] *= np.where((d >= np.datetime64("2025-04-01")) & (d < np.datetime64("2025-06-01")), 1.6, 1.0)   # price-rise notices
    W[:, 3] *= np.where(d >= np.datetime64("2024-11-04"), 1.2, 1.0)
    W[:, 8] = np.where((ctry == COUNTRIES.index[COUNTRIES.country_code == "GB"][0]) & (d >= np.datetime64("2025-07-25")), 0.35, 0)
    cat = (rng.random(N)[:, None] > np.cumsum(W / W.sum(1, keepdims=True), 1)).sum(1).clip(0, len(CATS) - 1)
    # refund tickets tied to actual refunds
    rf = tx[tx.type.isin([4, 5])]
    rdate = pd.to_datetime(rf.date).to_numpy().astype("datetime64[D]") - rng.integers(0, 3, len(rf)).astype("timedelta64[D]")
    rdate = np.maximum(rdate, days[0])
    d = np.r_[d, rdate]
    sid = np.r_[sid, rf.sid.to_numpy()]
    ctry = np.r_[ctry, s.country.to_numpy()[rf.sid]]
    cat = np.r_[cat, np.ones(len(rf), int)]
    is_prem = np.r_[is_prem, np.ones(len(rf), bool)]
    refund_amt = np.r_[np.zeros(N), -rf.gross_usd.to_numpy()]
    N = len(d)
    # channel, priority, SLA
    chat_era = d >= np.datetime64("2025-09-01")
    u = rng.random(N)
    channel = np.where(chat_era, np.select([u < 0.38, u < 0.65], ["Email", "Web form"], "Live chat"),
                       np.where(u < 0.55, "Email", "Web form"))
    high_cat = np.isin(cat, [0, 1, 4])
    u = rng.random(N)
    pr = np.select([u < 0.03, u < np.where(high_cat, 0.35, 0.17), u < 0.80], ["Urgent", "High", "Normal"], "Low")
    sla = np.where(channel == "Live chat", 0.25, pd.Series(pr).map({"Urgent": 2, "High": 8, "Normal": 24, "Low": 48}).to_numpy())
    # load vs capacity -> first response time
    vol = pd.Series(1, index=pd.DatetimeIndex(d)).groupby(level=0).size().reindex(di, fill_value=0)
    cap = vol.shift(45).rolling(30, min_periods=1).mean().bfill().to_numpy() * 1.02
    cap *= np.where(days >= np.datetime64("2025-03-01"), 1.05, 1.0)
    load = (vol.to_numpy() / cap)[(d - days[0]).astype(int)]
    base = pd.Series(channel).map({"Email": 9.0, "Web form": 10.0, "Live chat": 0.08}).to_numpy()
    base *= np.where(d >= np.datetime64("2025-03-01"), 0.8, 1.0)
    base *= pd.Series(pr).map({"Urgent": 0.3, "High": 0.6, "Normal": 1.0, "Low": 1.3}).to_numpy()
    frt = base * np.maximum(0.6, load) ** 2.2 * np.exp(rng.normal(0, 0.6, N))
    res = frt + CATS.res_h.to_numpy()[cat] * np.exp(rng.normal(0, 0.7, N)) * np.where(load > 1.1, 1.5, 1.0)
    sla_met = frt <= sla
    reopened = rng.random(N) < np.where(np.isin(cat, [6, 7]), 0.10, 0.06)
    # resolution text
    resolution = np.array([RESOLUTIONS[CATS.category[c]][0] for c in cat], dtype=object)
    alt = rng.random(N) < 0.35
    for c, opts in enumerate(RESOLUTIONS.values()):
        if len(opts) > 1:
            resolution[(cat == c) & alt] = opts[1]
    resolution[refund_amt > 0] = "Refund issued"
    # CSAT (about a quarter of tickets answer the survey)
    latent = (4.1 - 0.9 * ~sla_met - 1.4 * (resolution == "Refund denied") + 0.3 * (resolution == "Refund issued")
              - 0.4 * reopened - 0.5 * (resolution == "Verification failed") + rng.normal(0, 0.8, N))
    csat = np.where(rng.random(N) < 0.24, np.clip(np.round(latent), 1, 5), np.nan)
    secs = (rng.choice(24, N, p=HOUR_W / HOUR_W.sum()) * 3600 + rng.integers(0, 3600, N)).astype("timedelta64[s]")
    created = d.astype("datetime64[s]") + secs
    order = np.argsort(created, kind="stable")
    out = pd.DataFrame({
        "created_at": created, "subscriber_id": np.where(sid >= 0, [f"S{i + 1:07d}" for i in np.clip(sid, 0, None)], ""),
        "user_type": np.where(is_prem, "Premium", "Free"), "country_code": CODES[ctry], "contact_channel": channel,
        "category": CATS.category.to_numpy()[cat], "priority": pr, "assigned_team": CATS.team.to_numpy()[cat],
        "sla_target_hours": sla, "first_response_hours": frt.round(2), "resolution_hours": res.round(2),
        "sla_met": sla_met, "reopened": reopened, "resolution": resolution, "refund_amount_usd": refund_amt.round(2),
        "csat_score": csat}).iloc[order].reset_index(drop=True)
    out.insert(0, "ticket_id", [f"T{i + 1:07d}" for i in range(len(out))])
    return out
