"""Aggregate the dataset CSVs into one compact JSON for the dashboard.

    python tools/build_dashboard_data.py    ->  data/dashboard.json
"""
import json
import os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "dataset", "csv")
OUT = os.path.join(ROOT, "data", "dashboard.json")
LAST = "2026-08"
L12 = [f"2025-{m:02d}" for m in range(9, 13)] + [f"2026-{m:02d}" for m in range(1, 9)]


def rd(name, **kw):
    return pd.read_csv(os.path.join(CSV, f"{name}.csv"), **kw)


def r(x, n=4):
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return None
    return round(float(x), n)


def series(df, col, n=4):
    return [r(v, n) for v in df[col]]


kpi_m = rd("fact_kpi_monthly")
months = kpi_m.month.tolist()
bridge = rd("fact_mrr_bridge_monthly")
subs = rd("fact_subscribers", low_memory=False)
coh = rd("fact_cohort_retention")
mkt = rd("fact_marketing_daily")
mkt["month"] = mkt.date.str[:7]
pnl = rd("fact_pnl_monthly")
gpu = rd("fact_gpu_daily")
gpu["month"] = gpu.date.str[:7]
pay = rd("fact_payments_monthly")
usage = rd("fact_usage_daily")
usage["month"] = usage.date.str[:7]
events = rd("dim_business_events")
ret_mx = rd("cohort_retention_matrix")
ltv_mx = rd("cohort_ltv_matrix")

out = {"meta": {"actual_through": LAST, "currency": "USD", "generated": pd.Timestamp.today().strftime("%Y-%m-%d"),
                "months": months}}


def kpi(idx, label, col, unit, fmt, note=""):
    s = kpi_m[col]
    cur, prev = s.iloc[-1], s.iloc[-13]
    return {"id": idx, "label": label, "value": r(cur), "prev": r(prev),
            "change": r((cur / prev - 1) if prev else None), "unit": unit, "format": fmt,
            "spark": series(kpi_m, col), "note": note}


out["kpis"] = [
    kpi("arr", "Subscription ARR", "arr_eom_usd", "usd", "musd", "Month-end MRR x 12"),
    kpi("revenue", "Net revenue, run-rate", "net_revenue_usd", "usd", "musd12", "Latest month x 12"),
    kpi("subs", "Active subscribers", "active_subscribers_eom", "count", "kcount", ""),
    kpi("gm", "Gross margin", "gross_margin", "pct", "pct1", ""),
    kpi("ebitda", "EBITDA margin", "ebitda_margin", "pct", "pct1", ""),
    kpi("cac", "Blended CAC", "blended_cac_usd", "usd", "usd2", "All channels incl. organic"),
]

cols = ["month", "active_subscribers_eom", "new_subscribers", "reactivated_subscribers", "churned_subscribers",
        "monthly_churn_rate", "mrr_eom_usd", "arr_eom_usd", "net_new_mrr_usd", "subscription_revenue_usd",
        "token_revenue_usd", "net_revenue_usd", "token_share_of_revenue", "subscription_billings_usd",
        "deferred_revenue_eom_usd", "gross_margin", "ebitda_usd", "ebitda_margin", "acquisition_spend_usd",
        "blended_cac_usd", "paid_cac_usd", "arpu_usd", "token_attach_rate", "token_arppu_usd",
        "annual_plan_share_of_actives", "signup_to_paid_cvr", "m1_retention_prior_cohort", "gpu_cost_usd",
        "gpu_cost_per_active_sub_usd", "gpu_cost_pct_revenue", "free_tier_compute_cost_usd", "tickets_per_1k_subs",
        "sla_met_rate", "avg_csat", "renewal_approval_rate", "card_chargeback_ratio", "headcount_eom"]
out["monthly"] = json.loads(kpi_m[cols].round(4).to_json(orient="records"))

mv = ["mrr_new", "mrr_reactivation", "mrr_expansion", "mrr_contraction", "mrr_fx", "mrr_churn_voluntary",
      "mrr_churn_involuntary", "mrr_churn_refund", "mrr_churn_chargeback"]
b = bridge.groupby("month")[["mrr_start", "mrr_end"] + mv].sum().round(0)
out["mrr_movements"] = [{"month": m, **{k.replace("mrr_", ""): r(v, 0) for k, v in row.items()}}
                        for m, row in b.iterrows()]
w = b.loc[L12]
out["waterfall"] = {"period": f"{L12[0]} to {L12[-1]}",
                    "start": r(w.mrr_start.iloc[0], 0), "end": r(w.mrr_end.iloc[-1], 0),
                    "steps": [{"label": lab, "value": r(w[c].sum(), 0)} for lab, c in
                              [("New", "mrr_new"), ("Win-back", "mrr_reactivation"), ("Expansion", "mrr_expansion"),
                               ("Contraction", "mrr_contraction"), ("FX", "mrr_fx"),
                               ("Voluntary churn", "mrr_churn_voluntary"),
                               ("Payment-failure churn", "mrr_churn_involuntary"),
                               ("Refunds & chargebacks", "mrr_churn_refund")]]}
out["waterfall"]["steps"][-1]["value"] = r(w[["mrr_churn_refund", "mrr_churn_chargeback"]].sum().sum(), 0)

ch_names = rd("dim_channel").set_index("channel_id")
m12 = mkt[mkt.month.isin(L12) & (mkt.channel_id != "CH10")]
spend12 = m12.groupby("channel_id").spend_usd.sum()
new12 = m12.groupby("channel_id").new_paid_subscribers.sum()
k12 = kpi_m[kpi_m.month.isin(L12)]
gm = float(k12.gross_profit_usd.sum() / k12.net_revenue_usd.sum())
mature = [f"2024-{m:02d}" for m in range(1, 13)] + [f"2025-{m:02d}" for m in range(1, 9)]
rows = []
for cid in sorted(spend12.index):
    c = coh[(coh.channel_id == cid) & coh.cohort_month.isin(mature)]
    curve = c.groupby("months_since_first_payment")[["cum_net_revenue_usd", "cohort_size"]].sum()
    per = curve.cum_net_revenue_usd / curve.cohort_size
    recent = coh[(coh.channel_id == cid) & (coh.months_since_first_payment == 1) & coh.cohort_month.isin(L12)]
    cac = float(spend12[cid] / new12[cid]) if new12.get(cid, 0) else 0.0
    pay_m = None
    if cac > 0:
        gp = per * gm
        hit = gp[gp >= cac]
        if len(hit):
            k = int(hit.index[0])
            prev = gp.get(k - 1, 0.0)
            pay_m = k - 1 + (cac - prev) / (gp[k] - prev) if k > 0 and gp[k] > prev else float(k)
    rows.append({"id": cid, "name": ch_names.channel[cid], "group": ch_names.channel_group[cid],
                 "subs_12m": int(new12.get(cid, 0)), "spend_12m": r(spend12[cid], 0), "cac": r(cac, 2),
                 "ltv6": r(per.get(6)), "ltv12": r(per.get(12)), "ltv24": r(per.get(24)),
                 "ltv_cac": r(per.get(12) / cac if cac else None, 2), "payback_months": r(pay_m, 2),
                 "m1_retention": r(recent.active_subscribers.sum() / recent.cohort_size.sum() if len(recent) else None),
                 "curve": [r(per.get(i)) for i in range(0, 25)]})
out["channels"] = rows
out["meta"]["gross_margin_12m"] = r(gm)

q = mkt[mkt.channel_id != "CH10"].copy()
q["quarter"] = pd.PeriodIndex(q.month, freq="M").asfreq("Q").astype(str)
qa = q.groupby(["quarter", "channel_id"]).agg(s=("spend_usd", "sum"), n=("new_paid_subscribers", "sum"))
cacq = (qa.s / qa.n).unstack().round(2)
out["cac_quarterly"] = {"quarters": cacq.index.tolist(),
                        "series": {c: [r(v, 2) for v in cacq[c]] for c in cacq.columns if cacq[c].notna().any()}}

mcols = [c for c in ret_mx.columns if c.startswith("M")]
out["cohort"] = {"months": ret_mx.cohort_month.tolist(), "sizes": ret_mx.cohort_size.tolist(),
                 "retention": [[r(v, 4) for v in row] for row in ret_mx[mcols].to_numpy()],
                 "ltv": [[r(v, 2) for v in row] for row in ltv_mx[mcols].to_numpy()]}

mix = subs[subs.cohort_month >= "2024-01"].pivot_table(index="cohort_month", columns="first_plan_id",
                                                       values="subscriber_id", aggfunc="count").fillna(0)
mix = mix.div(mix.sum(1), axis=0).reindex(months)
out["plan_mix"] = [{"month": m, **{p: r(mix.loc[m, p]) for p in ["P1M", "P3M", "P12M"]}} for m in months]
out["mrr_per_sub"] = [r(v, 2) for v in (kpi_m.mrr_eom_usd / kpi_m.active_subscribers_eom)]

g = gpu.pivot_table(index="month", columns="workload", values="cost_usd", aggfunc="sum").reindex(months).fillna(0)
out["compute"] = {"workloads": g.columns.tolist(), "series": {c: [r(v, 0) for v in g[c]] for c in g.columns}}
u = usage.pivot_table(index="month", columns="user_type", values="compute_cost_usd", aggfunc="sum").reindex(months)
out["compute"]["free_vs_premium"] = {c: [r(v, 0) for v in u[c]] for c in u.columns}
feat = usage[usage.month.isin(L12)].groupby("feature_id")[["units", "tokens_consumed", "compute_cost_usd"]].sum()
fn = rd("dim_feature").set_index("feature_id")
out["features"] = [{"feature": fn.feature[i], "units": int(v.units), "tokens": int(v.tokens_consumed),
                    "cost": r(v.compute_cost_usd, 0)} for i, v in feat.iterrows()]

ren = pay[pay.payment_type == "Renewal"].pivot_table(index="month", columns="processor_id",
                                                     values=["approved", "attempts"], aggfunc="sum")
appr = (ren["approved"] / ren["attempts"]).reindex(months)
out["payments"] = {"processors": appr.columns.tolist(),
                   "approval": {c: [r(v) for v in appr[c]] for c in appr.columns}}

ytd = [f"2026-{m:02d}" for m in range(1, 9)]
p = pnl[pnl.month.isin(ytd)].pivot_table(index=["line_id", "line_item", "section"], columns="scenario",
                                         values="amount_usd", aggfunc="sum").reset_index()
p["var"] = p["Actual"] - p["Budget"]
out["bva"] = [{"line": row.line_item, "section": row.section, "actual": r(row.Actual, 0), "budget": r(row.Budget, 0),
               "var": r(row["var"], 0)} for _, row in p.sort_values("var").iterrows()]
q2 = pnl[pnl.scenario.isin(["Actual", "Forecast"])].copy()
q2["quarter"] = pd.PeriodIndex(q2.month, freq="M").asfreq("Q").astype(str)
sec = q2.pivot_table(index="quarter", columns="section", values="amount_usd", aggfunc="sum").fillna(0)
opex = [c for c in sec.columns if c.startswith("Opex")]
out["pnl_quarterly"] = [{"quarter": qq, "revenue": r(row["Revenue"], 0), "cogs": r(row["COGS"], 0),
                         "opex": r(row[opex].sum(), 0),
                         "ebitda": r(row["Revenue"] + row["COGS"] + row[opex].sum(), 0),
                         "margin": r((row["Revenue"] + row["COGS"] + row[opex].sum()) / row["Revenue"])}
                        for qq, row in sec.iterrows()]

seg = subs.groupby("token_spend_segment").agg(subs=("subscriber_id", "count"), rev=("token_net_revenue_usd", "sum"))
seg = seg.reindex(["Whale", "Heavy", "Medium", "Light", "Non-buyer"]).dropna()
out["token_segments"] = [{"segment": i, "subs": int(v.subs), "revenue": r(v.rev, 0),
                          "share_subs": r(v.subs / seg.subs.sum()), "share_revenue": r(v.rev / seg.rev.sum())}
                         for i, v in seg.iterrows()]

out["events"] = json.loads(events.to_json(orient="records"))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, separators=(",", ":"))
print("wrote", OUT, round(os.path.getsize(OUT) / 1024, 1), "KB")
for c in out["channels"]:
    print(f"  {c['name']:26s} CAC {c['cac']:6.2f}  LTV12 {c['ltv12']:7.2f}  payback {c['payback_months']}  m1 {c['m1_retention']}")

# a JS copy so the page also works when opened straight from disk (file://)
with open(os.path.join(ROOT, "data", "dashboard.js"), "w", encoding="utf-8") as f:
    f.write("window.DASHBOARD_DATA = ")
    json.dump(out, f, separators=(",", ":"))
    f.write(";\n")
print("wrote data/dashboard.js")
