"""Run the full pipeline: simulate, build every table, reconcile, export.

    python build.py            -> writes ../csv/*.csv, ../Candy_AI_BizOps_Dataset.xlsx
"""
import sys
import time
import numpy as np
import pandas as pd
import config as C
from acquisition import build_dim_date, build_cells
from simulate import create_subscribers, simulate
import marts_core as mc
import marts_growth as mg
import marts_ops as mo
import finance as fin


def dims(dd, exp_dim):
    pb = C.PRICE_BOOK.copy()
    for p, per in (("p1m", 1), ("p3m", 3), ("p12m", 12)):
        pb[f"{p}_billed"] = (pb[f"{p}_per_month"] * per).round(2)
        pb[f"{p}_discount_vs_monthly"] = (1 - pb[f"{p}_per_month"] / pb.p1m_per_month).round(3)
    plan = C.PLANS.assign(current_price_per_month=[13.99, 8.99, 3.99], current_billed_amount=[13.99, 26.97, 47.88],
                          list_price_per_month=13.99, current_discount=[0.0, 0.35, 0.70], tokens_per_month=100)
    return {
        "dim_date": dd.assign(date=dd.date.dt.date),
        "dim_country": C.COUNTRIES.drop(columns=["_w24", "_w26"]),
        "dim_channel": C.CHANNELS.drop(columns=["_quality", "_token_mult", "_crypto_share"]),
        "dim_campaign": C.CAMPAIGNS.drop(columns=["_s", "_e", "_w"]),
        "dim_plan": plan, "dim_price_book": pb, "dim_token_pack": C.TOKEN_PACKS,
        "dim_payment_method": C.PAY_METHODS, "dim_processor": C.PROCESSORS, "dim_feature": C.FEATURES,
        "dim_gpu_cluster": mo.CLUSTERS,
        "dim_fx_monthly": pd.DataFrame({"month": mc.MSTR, "usd_per_eur": C.EURUSD, "usd_per_gbp": C.GBPUSD}),
        "dim_experiment": exp_dim, "dim_business_events": fin.dim_events(),
        "dim_pnl_line": pd.DataFrame(fin.LINES, columns=["line_id", "line_item", "section"]).assign(sort_order=range(1, len(fin.LINES) + 1)),
    }


def kpi_monthly(T, out, act, s):
    b = T["fact_mrr_bridge_monthly"].groupby("month").sum(numeric_only=True)
    m = pd.DataFrame(index=mc.MSTR)
    m["active_subscribers_eom"] = b.subs_end
    m["new_subscribers"], m["reactivated_subscribers"] = b.new_subs, b.reactivated_subs
    churn_cols = ["churned_voluntary_subs", "churned_involuntary_subs", "churned_refund_subs", "churned_chargeback_subs"]
    m["churned_subscribers"] = b[churn_cols].sum(1)
    m["voluntary_churn_subs"], m["involuntary_churn_subs"] = b.churned_voluntary_subs, b.churned_involuntary_subs
    m["monthly_churn_rate"] = b[churn_cols].sum(1) / b.subs_start.replace(0, np.nan)
    m["mrr_eom_usd"], m["net_new_mrr_usd"] = b.mrr_end, b.mrr_net_new
    m["arr_eom_usd"] = b.mrr_end * 12
    nr = act["R1"] + act["R2"] + act["R3"]
    m["subscription_revenue_usd"], m["token_revenue_usd"], m["refunds_chargebacks_usd"] = act["R1"], act["R2"], act["R3"]
    m["net_revenue_usd"] = nr
    m["token_share_of_revenue"] = act["R2"] / (act["R1"] + act["R2"])
    rd = T["fact_revenue_monthly"]
    bill = rd[rd.txn_type.isin(["New subscription", "Renewal", "Reactivation"])].groupby("month").net_usd.sum()
    m["subscription_billings_usd"] = bill
    m["deferred_revenue_eom_usd"] = T["fact_deferred_revenue"].set_index("month").deferred_revenue_closing_usd
    cogs = sum(act[k] for k in ("C1", "C2", "C3", "C4", "C5", "C6"))
    opex = sum(act[k] for k in act if k.startswith("O"))
    m["gross_profit_usd"], m["gross_margin"] = nr + cogs, (nr + cogs) / nr
    m["total_opex_usd"], m["ebitda_usd"] = -opex, nr + cogs + opex
    m["ebitda_margin"] = m.ebitda_usd / nr
    mk = T["fact_marketing_daily"].assign(month=lambda d: pd.to_datetime(d.date).dt.to_period("M").astype(str))
    acq = mk[mk.channel_id != "CH10"]
    paid = acq.channel_id.isin(["CH01", "CH02", "CH03", "CH04", "CH08", "CH09"])
    m["acquisition_spend_usd"] = acq.groupby("month").spend_usd.sum()
    m["blended_cac_usd"] = m.acquisition_spend_usd / m.new_subscribers
    m["paid_cac_usd"] = acq[paid].groupby("month").spend_usd.sum() / acq[paid].groupby("month").new_paid_subscribers.sum()
    avg_subs = (b.subs_start + b.subs_end) / 2
    m["arpu_usd"] = nr / avg_subs
    tokb = out["tx"][out["tx"].type == 3].groupby("t").sid.nunique().to_numpy()
    m["token_buyers"] = tokb
    m["token_attach_rate"] = tokb / avg_subs
    m["token_arppu_usd"] = act["R2"] / tokb
    ann = T["fact_mrr_bridge_monthly"].pivot_table(index="month", columns="plan_id", values="subs_end", aggfunc="sum")
    m["annual_plan_share_of_actives"] = ann["P12M"] / ann.sum(1)
    fu = T["fact_funnel_daily"].assign(month=lambda d: pd.to_datetime(d.date).dt.to_period("M").astype(str)).groupby("month")
    m["free_signups"] = fu.free_signups.sum()
    m["signup_to_paid_cvr"] = m.new_subscribers / m.free_signups
    cf = T["fact_cohort_retention"]
    m1 = cf[cf.months_since_first_payment == 1].groupby("cohort_month")[["active_subscribers", "cohort_size"]].sum()
    m1r = m1.active_subscribers / m1.cohort_size
    m1r.index = [str(pd.Period(c, "M") + 1) for c in m1r.index]          # cohort c's M1 is observed in month c+1
    m["m1_retention_prior_cohort"] = m1r.reindex(mc.MSTR).to_numpy()
    us = T["fact_usage_daily"].assign(month=lambda d: pd.to_datetime(d.date).dt.to_period("M").astype(str))
    m["gpu_cost_usd"] = us.groupby("month").compute_cost_usd.sum()
    m["gpu_cost_per_active_sub_usd"] = m.gpu_cost_usd / avg_subs
    m["gpu_cost_pct_revenue"] = m.gpu_cost_usd / nr
    m["free_tier_compute_cost_usd"] = us[us.user_type == "Free"].groupby("month").compute_cost_usd.sum()
    um = us.pivot_table(index="month", columns="feature_id", values="units", aggfunc="sum")
    m["chat_messages_m"], m["images_generated_k"] = um.F01 / 1e6, um.F04 / 1e3
    m["videos_generated_k"] = um.F05.reindex(mc.MSTR).fillna(0) / 1e3
    tk = T["fact_support_tickets"].assign(month=lambda d: pd.to_datetime(d.created_at).dt.to_period("M").astype(str)).groupby("month")
    m["support_tickets"] = tk.size()
    m["tickets_per_1k_subs"] = m.support_tickets / avg_subs * 1000
    m["sla_met_rate"], m["avg_csat"] = tk.sla_met.mean(), tk.csat_score.mean()
    pay = T["fact_payments_monthly"]
    ren = pay[pay.payment_type == "Renewal"].groupby("month")[["approved", "attempts"]].sum()
    m["renewal_approval_rate"] = ren.approved / ren.attempts
    card = pay[pay.processor_id != "CRYPTO_GW"]
    cbk = card[card.payment_type == "Chargeback"].groupby("month").transactions.sum()
    sales = card[card.payment_type.isin(["Initial (new + win-back)", "Renewal", "Token pack"])].groupby("month").approved.sum()
    m["card_chargeback_ratio"] = (cbk / sales).reindex(mc.MSTR).fillna(0)
    hc = T["fact_headcount_monthly"].groupby("month").headcount_eom.sum()
    m["headcount_eom"] = hc
    m["annualised_revenue_per_fte_usd"] = nr * 12 / hc
    m = m.reset_index().rename(columns={"index": "month"})
    num = m.select_dtypes("number").columns
    m[num] = m[num].astype(float).round(4)
    return m


def model_drivers(T):
    k = T["fact_kpi_monthly"].set_index("month")
    p = T["fact_pnl_monthly"]
    per = {"fy25": [f"2025-{i:02d}" for i in range(1, 13)], "ytd": [f"2026-{i:02d}" for i in range(1, 9)]}
    mk = T["fact_marketing_daily"].assign(month=lambda d: pd.to_datetime(d.date).dt.to_period("M").astype(str))
    subs = T["fact_subscribers"]
    coh = T["fact_cohort_retention"]
    hc = T["fact_headcount_monthly"]

    def val(name, months):
        kk = k.loc[months]
        a = p[(p.scenario == "Actual") & p.month.isin(months)]
        nr = a[a.section == "Revenue"].amount_usd.sum()
        m = mk[mk.month.isin(months) & (mk.channel_id != "CH10")]
        paid = m.channel_id.isin(["CH01", "CH02", "CH03", "CH04", "CH08", "CH09"])
        c1 = coh[(coh.months_since_first_payment == 1) & coh.cohort_month.isin(months)]
        sb = subs[subs.cohort_month.isin(months)]
        h = hc[hc.month.isin(months)]
        return {
            "new": kk.new_subscribers.mean(), "cac": m.spend_usd.sum() / m.new_paid_subscribers.sum(),
            "paid_cac": m[paid].spend_usd.sum() / m[paid].new_paid_subscribers.sum(),
            "organic": m[~paid].new_paid_subscribers.sum() / m.new_paid_subscribers.sum(),
            "annual": (sb.first_plan_id == "P12M").mean(), "m1": c1.active_subscribers.sum() / c1.cohort_size.sum(),
            "churn": kk.monthly_churn_rate.mean(), "attach": kk.token_attach_rate.mean(), "arppu": kk.token_arppu_usd.mean(),
            "arpu": kk.arpu_usd.mean(), "cvr": kk.signup_to_paid_cvr.mean(), "gpu_sub": kk.gpu_cost_per_active_sub_usd.mean(),
            "free": kk.free_tier_compute_cost_usd.mean(), "fees": -a[a.line_id.isin(["C3", "C4"])].amount_usd.sum() / nr,
            "renew": kk.renewal_approval_rate.mean(), "hc": kk.headcount_eom.iloc[-1],
            "payroll_fte": h.fully_loaded_cost_usd.sum() / h.headcount_eom.sum(), "gm": kk.gross_profit_usd.sum() / nr,
            "ebitda": kk.ebitda_usd.sum() / nr}

    a, b = val("fy25", per["fy25"]), val("ytd", per["ytd"])
    spec = [  # key, driver, unit, downside x, base x, upside x (applied to FY26 YTD), note
        ("new", "New paid subscribers per month", "subscribers", 1.00, 1.22, 1.45, "Average monthly first payments"),
        ("cac", "Blended CAC", "USD", 1.20, 1.05, 0.95, "Acquisition spend / all new subscribers"),
        ("paid_cac", "Paid CAC", "USD", 1.25, 1.06, 0.95, "Paid-channel spend / paid-channel first payments"),
        ("organic", "Organic share of new subscribers", "%", 0.92, 1.00, 1.08, "SEO, direct, community"),
        ("annual", "12-month plan share of new subscribers", "%", 1.10, 1.00, 0.95, "Higher annual mix: more cash now, lower MRR per sub"),
        ("m1", "Month-1 retention", "%", 0.96, 1.00, 1.03, "Cohort active at M1 / cohort size"),
        ("churn", "Monthly churn rate", "%", 1.12, 1.00, 0.92, "Churned / opening subscribers"),
        ("attach", "Token attach rate", "%", 0.92, 1.03, 1.10, "Token buyers / average active subscribers"),
        ("arppu", "Token ARPPU", "USD per buyer per month", 0.95, 1.02, 1.06, "Token revenue / token buyers"),
        ("arpu", "ARPU", "USD per sub per month", 0.96, 1.01, 1.04, "Net revenue / average active subscribers"),
        ("cvr", "Sign-up to paid conversion", "%", 0.95, 1.02, 1.06, "New subscribers / free sign-ups"),
        ("gpu_sub", "GPU cost per active subscriber", "USD per month", 1.15, 0.95, 0.85, "Includes free-tier load"),
        ("free", "Free-tier compute cost", "USD per month", 1.25, 1.10, 0.95, "Grows with sign-ups; lever: message cap"),
        ("fees", "Payment fees incl. chargebacks", "% of net revenue", 1.08, 0.98, 0.94, "More Acquirer C and crypto lowers fees"),
        ("renew", "Renewal approval rate", "%", 0.99, 1.00, 1.005, "After retries"),
        ("hc", "Headcount (end of period)", "FTE", 1.10, 1.25, 1.35, "Upside grows faster and hires more"),
        ("payroll_fte", "Payroll cost per FTE", "USD per month", 1.06, 1.04, 1.03, "Fully loaded"),
        ("gm", "Gross margin", "%", 0.95, 1.01, 1.03, "Net revenue - COGS"),
        ("ebitda", "EBITDA margin", "%", 0.40, 1.15, 1.45, "Outcome check for the plan"),
    ]
    rows = [(d, u, a[kk], b[kk], b[kk] * lo, b[kk] * base, b[kk] * hi, note) for kk, d, u, lo, base, hi, note in spec]
    df = pd.DataFrame(rows, columns=["driver", "unit", "fy2025_actual", "fy2026_ytd_actual", "fy2027_downside",
                                     "fy2027_base", "fy2027_upside", "notes"])
    num = ["fy2025_actual", "fy2026_ytd_actual", "fy2027_downside", "fy2027_base", "fy2027_upside"]
    df[num] = df[num].astype(float).round(4)
    return df


def build():
    t0 = time.time()
    rng = np.random.default_rng(C.SEED)
    dd = build_dim_date()
    cells = build_cells(dd, rng)
    s = create_subscribers(cells, dd, rng)
    s, out = simulate(s, rng)
    tx = mc.add_dates(out["tx"])
    print(f"simulated {len(s):,} subscribers, {len(tx):,} transactions in {time.time() - t0:.1f}s")
    T = {}
    T["fact_subscribers"] = mc.fact_subscribers(s, tx)
    T["fact_mrr_bridge_monthly"] = mc.fact_mrr_bridge(out["bridge"])
    T["fact_cohort_retention"] = mc.fact_cohorts(s, out["cohort"])
    T["cohort_retention_matrix"], T["cohort_ltv_matrix"] = mc.cohort_matrices(T["fact_cohort_retention"])
    T["fact_revenue_daily"] = mc.fact_revenue_daily(tx, s)
    T["fact_revenue_monthly"] = mc.fact_revenue_monthly(T["fact_revenue_daily"])
    T["fact_recognized_revenue_monthly"], T["fact_deferred_revenue"] = mc.fact_recognized_revenue(out)
    T["fact_payments_monthly"] = mc.fact_payments(tx, out["ren"], s, rng)
    T["fact_marketing_daily"] = mg.fact_marketing_daily(cells, s, tx, rng)
    T["fact_funnel_daily"] = mg.fact_funnel_daily(cells, rng)
    exp_dim, T["fact_experiment_daily"] = mg.experiments(s, T["fact_funnel_daily"], rng)
    T["fact_usage_daily"] = mo.fact_usage_daily(dd, out["bridge"], T["fact_funnel_daily"], tx, rng)
    T["fact_gpu_daily"] = mo.fact_gpu_daily(T["fact_usage_daily"], rng)
    T["fact_support_tickets"] = mo.fact_support_tickets(dd, s, tx, out["active_idx"], T["fact_usage_daily"], rng)
    T["fact_headcount_monthly"] = fin.fact_headcount(rng)
    act = fin.pnl_actual(out["rec"], out["contra"], tx, T["fact_usage_daily"], T["fact_marketing_daily"],
                         T["fact_support_tickets"], T["fact_funnel_daily"], T["fact_headcount_monthly"])
    T["fact_pnl_monthly"] = fin.fact_pnl(act, fin.pnl_budget(act), fin.pnl_forecast(act))
    T["fact_pnl_monthly"]["year"] = T["fact_pnl_monthly"].month.str[:4].astype(int)
    T["fact_pnl_monthly"]["month_num"] = T["fact_pnl_monthly"].month.str[5:].astype(int)
    T["fact_kpi_monthly"] = kpi_monthly(T, out, act, s)
    T["fin_model_drivers"] = model_drivers(T)
    T.update(dims(dd, exp_dim))
    print(f"built {len(T)} tables in {time.time() - t0:.1f}s")
    return T, out, tx, s


def reconcile(T, out, tx):
    b = T["fact_mrr_bridge_monthly"].groupby("month").sum(numeric_only=True)
    mv = [c for c in b.columns if c.startswith("mrr_") and c not in ("mrr_start", "mrr_end", "mrr_net_new")]
    new = int((T["fact_subscribers"].cohort_month >= "2024-01").sum())
    legacy_active = out["cohort"][out["cohort"].cohort < 0].groupby("t").active_end.sum().reindex(range(C.NM), fill_value=0).to_numpy()
    cohort_active = T["fact_cohort_retention"].groupby("calendar_month").active_subscribers.sum().to_numpy()
    checks = [  # name, difference, tolerance (money checks allow cent rounding across rows)
        ("MRR bridge: start + movements = end", (b.mrr_start + b[mv].sum(1) - b.mrr_end).abs().max(), 5),
        ("MRR bridge: end(t) = start(t+1)", (b.mrr_end.shift(1) - b.mrr_start).iloc[1:].abs().max(), 5),
        ("New subscribers = bridge new subs", new - b.new_subs.sum(), 0),
        ("New subscribers = marketing new paid", new - T["fact_marketing_daily"].new_paid_subscribers.sum(), 0),
        ("New subscribers = funnel new paid", new - T["fact_funnel_daily"].new_paid_subscribers.sum(), 0),
        ("Revenue daily net = transactions net", T["fact_revenue_daily"].net_usd.sum() - tx.net_usd.sum(), 100),
        ("Subscriber lifetime revenue = transactions", T["fact_subscribers"].lifetime_net_revenue_usd.sum() - tx.net_usd.sum(), 100),
        ("GPU clusters = usage compute cost", T["fact_gpu_daily"].cost_usd.sum() - T["fact_usage_daily"].compute_cost_usd.sum(), 100),
        ("Cohorts + 2023 base = bridge active", np.abs(cohort_active + legacy_active - b.subs_end.to_numpy()).max(), 0),
        ("Payments initial approved = new + win-back",
         T["fact_payments_monthly"].query("payment_type == 'Initial (new + win-back)'").approved.sum() - tx.type.isin([0, 2]).sum(), 0),
        ("Refund tickets = refund transactions", (T["fact_support_tickets"].resolution == "Refund issued").sum() - tx.type.isin([4, 5]).sum(), 0),
    ]
    for name, v, tol in checks:
        print(f"  {'OK ' if abs(v) <= tol else 'BAD'} {name}: {float(v):,.2f}")
    return all(abs(v) <= tol for _, v, tol in checks)


if __name__ == "__main__":
    T, out, tx, s = build()
    ok = reconcile(T, out, tx)
    for k, v in T.items():
        print(f"{k:34s} {len(v):>9,} rows x {v.shape[1]} cols")
    if "--export" in sys.argv:
        from export import export_all
        export_all(T)
