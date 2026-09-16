"""Subscriber, MRR, cohort, revenue and payments tables derived from the simulation."""
import numpy as np
import pandas as pd
from config import MONTHS, NM, COUNTRIES, CHANNELS, PLANS, TOKEN_PACKS, PAY_METHODS, PROCESSORS, TIER, PERIOD, mlabel
from acquisition import DEVICES
from simulate import TX_TYPES, DEC_INIT

CODES, CHIDS = COUNTRIES.country_code.to_numpy(), CHANNELS.channel_id.to_numpy()
PLAN_IDS, PACK_IDS = PLANS.plan_id.to_numpy(), TOKEN_PACKS.pack_id.to_numpy()
PM_IDS, PROC_IDS = PAY_METHODS.payment_method_id.to_numpy(), PROCESSORS.processor_id.to_numpy()
MSTR = np.array([str(m) for m in MONTHS])
TIERS = np.array(["Tier 1", "Tier 2", "Tier 3"])
CHURN_TYPES = np.array(["", "Voluntary", "Involuntary (payment failure)", "Refund", "Chargeback"])
FIRST_DAY = np.array([m.start_time for m in MONTHS], dtype="datetime64[D]")


def add_dates(tx):
    tx["date"] = FIRST_DAY[tx.t.to_numpy()] + (tx.day.to_numpy() - 1).astype("timedelta64[D]")
    tok = tx.type.isin([3, 5]).to_numpy()
    tx["product_id"] = np.where(tok, PACK_IDS[np.clip(tx.item, 0, 5)], PLAN_IDS[np.clip(tx.item, 0, 2)])
    return tx


def fact_subscribers(s, tx):
    n = len(s)
    net = tx.pivot_table(index="sid", columns="type", values="net_usd", aggfunc="sum", fill_value=0).reindex(range(n), fill_value=0)
    cnt = tx.pivot_table(index="sid", columns="type", values="net_usd", aggfunc="size", fill_value=0).reindex(range(n), fill_value=0)
    col = lambda df, c: df[c].to_numpy() if c in df.columns else np.zeros(n)
    toks = tx[tx.type == 3].assign(tk=lambda d: TOKEN_PACKS.tokens.to_numpy()[d.item]).groupby("sid").tk.sum().reindex(range(n), fill_value=0)
    sub_net = col(net, 0) + col(net, 1) + col(net, 2) + col(net, 4) + col(net, 6)
    tok_net = col(net, 3) + col(net, 5)
    seg = np.full(n, "Non-buyer", dtype=object)
    buy = tok_net > 0
    q = np.quantile(tok_net[buy], [0.5, 0.8, 0.95])
    seg[buy] = np.select([tok_net[buy] <= q[0], tok_net[buy] <= q[1], tok_net[buy] <= q[2]], ["Light", "Medium", "Heavy"], "Whale")
    lc = s.last_churn_m.to_numpy()
    fc = s.first_churn_m.to_numpy()
    return pd.DataFrame({
        "subscriber_id": [f"S{i + 1:07d}" for i in range(n)],
        "first_payment_date": s.date.dt.date, "cohort_month": mlabel(s.m),
        "country_code": CODES[s.country], "market_tier": TIERS[TIER[s.country]],
        "channel_id": CHIDS[s.channel], "campaign_id": s.campaign_id, "device": np.array(DEVICES)[s.device],
        "payment_method_id": PM_IDS[s.pm], "processor_id": PROC_IDS[s.proc_now],
        "first_plan_id": PLAN_IDS[s.plan0], "current_plan_id": PLAN_IDS[s.current_plan],
        "first_price_per_month": s.price0.round(2), "acquired_on_promo": s.promo,
        "pricing_experiment_variant": s.exp_variant,
        "status": s.status, "churn_month": np.where(lc >= 0, MSTR[np.clip(lc, 0, NM - 1)], ""),
        "churn_type": CHURN_TYPES[s.churn_type], "first_churn_month": np.where(fc >= 0, MSTR[np.clip(fc, 0, NM - 1)], ""),
        "months_active": s.months_active, "renewals": col(cnt, 1), "reactivations": s.reactivations,
        "token_packs_purchased": col(cnt, 3), "tokens_purchased": toks.to_numpy(),
        "first_payment_net_usd": s.first_payment_net_usd.round(2),
        "subscription_net_revenue_usd": sub_net.round(2), "token_net_revenue_usd": tok_net.round(2),
        "refunds_usd": (-(col(net, 4) + col(net, 5))).round(2) + 0.0, "chargebacks_usd": (-col(net, 6)).round(2) + 0.0,
        "lifetime_net_revenue_usd": (sub_net + tok_net).round(2),
        "current_mrr_usd": s.mrr_end_usd.round(2), "token_spend_segment": seg,
    })


def fact_mrr_bridge(bridge):
    b = bridge.copy()
    b.insert(0, "month", MSTR[b.pop("t")])
    b["country_code"], b["channel_id"], b["plan_id"] = CODES[b.country], CHIDS[b.channel], PLAN_IDS[b.plan]
    b = b.drop(columns=["country", "channel", "plan"])
    money = [c for c in b.columns if c.startswith("mrr")]
    b["mrr_net_new"] = b[money].drop(columns=["mrr_start", "mrr_end"]).sum(1)
    b[money + ["mrr_net_new"]] = b[money + ["mrr_net_new"]].round(2)
    front = ["month", "country_code", "channel_id", "plan_id"]
    return b[front + [c for c in b.columns if c not in front]]


def fact_cohorts(s, coh):
    keys = ["cohort", "channel", "plan0", "tier"]
    s = s[s.m >= 0]                                  # 2023 legacy cohorts have no M0 history -> excluded
    size = s.assign(cohort=s.m, tier=TIER[s.country], plan0=s.plan0.astype(int)).groupby(keys).size()
    coh = coh[coh.cohort >= 0].astype({"plan0": int})
    grid = [(c, ch, p, tr, c + k) for (c, ch, p, tr) in size.index for k in range(NM - c)]
    full = pd.DataFrame(grid, columns=keys + ["t"]).merge(coh, on=keys + ["t"], how="left").fillna(0)
    full["cohort_size"] = size.reindex(pd.MultiIndex.from_frame(full[keys])).to_numpy()
    full = full.sort_values(keys + ["t"])
    full["cum_net_revenue_usd"] = full.groupby(keys).cash_net.cumsum()
    out = pd.DataFrame({
        "cohort_month": MSTR[full.cohort.astype(int)], "months_since_first_payment": (full.t - full.cohort).astype(int),
        "calendar_month": MSTR[full.t.astype(int)], "channel_id": CHIDS[full.channel.astype(int)],
        "first_plan_id": PLAN_IDS[full.plan0.astype(int)], "market_tier": TIERS[full.tier.astype(int)],
        "cohort_size": full.cohort_size.astype(int), "active_subscribers": full.active_end.astype(int),
        "mrr_usd": full.mrr_end.round(2), "net_revenue_usd": full.cash_net.round(2),
        "cum_net_revenue_usd": full.cum_net_revenue_usd.round(2)})
    out["retention_rate"] = (out.active_subscribers / out.cohort_size).round(4)
    out["cum_net_revenue_per_sub_usd"] = (out.cum_net_revenue_usd / out.cohort_size).round(2)
    return out.reset_index(drop=True)


def cohort_matrices(cf):
    g = cf.groupby(["cohort_month", "months_since_first_payment"])[["cohort_size", "active_subscribers", "cum_net_revenue_usd"]].sum()
    ret = (g.active_subscribers / g.cohort_size).unstack()
    ltv = (g.cum_net_revenue_usd / g.cohort_size).unstack()
    size = g.cohort_size.groupby(level=0).first()
    fmt = lambda m, nd: m.round(nd).rename(columns=lambda k: f"M{k}").reset_index().assign(cohort_size=size.values)
    r, l = fmt(ret, 4), fmt(ltv, 2)
    cols = ["cohort_month", "cohort_size"] + [f"M{k}" for k in range(NM)]
    return r[cols], l[cols]


def fact_revenue_daily(tx, s):
    d = tx.assign(country=s.country.to_numpy()[tx.sid], fees=tx.fee_usd)
    g = d.groupby(["date", "country", "type", "product_id"]).agg(
        transactions=("net_usd", "size"), gross_usd=("gross_usd", "sum"), net_usd=("net_usd", "sum"),
        processing_fees_usd=("fees", "sum")).reset_index()
    g["tax_usd"] = g.gross_usd - g.net_usd
    g.insert(1, "country_code", CODES[g.pop("country")])
    g.insert(2, "txn_type", np.array(TX_TYPES)[g.pop("type")])
    g["date"] = pd.to_datetime(g.date).dt.date
    for c in ("gross_usd", "net_usd", "tax_usd", "processing_fees_usd"):
        g[c] = g[c].round(2)
    return g[["date", "country_code", "txn_type", "product_id", "transactions", "gross_usd", "tax_usd", "net_usd", "processing_fees_usd"]]


def fact_revenue_monthly(rd):
    m = rd.assign(month=pd.to_datetime(rd.date).dt.to_period("M").astype(str))
    return m.groupby(["month", "country_code", "txn_type", "product_id"], as_index=False)[
        ["transactions", "gross_usd", "tax_usd", "net_usd", "processing_fees_usd"]].sum().round(2)


def fact_payments(tx, ren, s, rng):
    """Grain: month x processor x payment method x payment type. Refunds / chargebacks are their own rows."""
    pm = s.pm.to_numpy()
    ptype = np.array(["Initial (new + win-back)", "Renewal", "Initial (new + win-back)", "Token pack",
                      "Refund", "Refund", "Chargeback"])
    d = tx.assign(pm=pm[tx.sid], payment_type=ptype[tx.type])
    keys = ["t", "proc", "pm", "payment_type"]
    g = d.groupby(keys).agg(transactions=("net_usd", "size"), amount_gross_usd=("gross_usd", "sum"),
                            processing_fees_usd=("fee_usd", "sum")).reset_index()
    r = ren.assign(pm=pm[ren.sid], payment_type="Renewal").groupby(keys).agg(
        attempts=("sid", "size"), declined_first_attempt=("declined", "sum"), recovered_by_retry=("recovered", "sum")).reset_index()
    g = g.merge(r, on=keys, how="outer").fillna(0)
    init = g.payment_type.isin(["Initial (new + win-back)", "Token pack"]).to_numpy()
    rate = DEC_INIT[g.proc.astype(int)] * np.where(g.payment_type == "Token pack", 0.6, 1.0) * np.exp(rng.normal(0, 0.06, len(g)))
    att_init = np.round(g.transactions / (1 - rate))
    g["attempts"] = np.where(init, att_init, g.attempts)
    g["declined_first_attempt"] = np.where(init, att_init - g.transactions, g.declined_first_attempt)
    g["failed_final"] = g.declined_first_attempt - g.recovered_by_retry
    g["approved"] = g.attempts - g.failed_final
    g["approval_rate"] = np.where(g.attempts > 0, g.approved / g.attempts.where(g.attempts > 0, 1), np.nan).round(4)
    g.insert(0, "month", MSTR[g.pop("t").astype(int)])
    g.insert(1, "processor_id", PROC_IDS[g.pop("proc").astype(int)])
    g.insert(2, "payment_method_id", PM_IDS[g.pop("pm").astype(int)])
    ints = ["transactions", "attempts", "declined_first_attempt", "recovered_by_retry", "failed_final", "approved"]
    g[ints] = g[ints].astype(int)
    g[["amount_gross_usd", "processing_fees_usd"]] = g[["amount_gross_usd", "processing_fees_usd"]].round(2)
    cols = ["month", "processor_id", "payment_method_id", "payment_type", "attempts", "declined_first_attempt",
            "recovered_by_retry", "failed_final", "approved", "approval_rate", "transactions", "amount_gross_usd", "processing_fees_usd"]
    return g[cols].sort_values(cols[:4]).reset_index(drop=True)


def fact_recognized_revenue(out):
    rec, contra, rb = out["rec"], out["contra"], out["rec_by_bill"]
    rows = []
    for t in range(NM):
        for c in range(len(CODES)):
            for p in range(3):
                if rec[t, c, p] or contra[t, c, p]:
                    rows.append((MSTR[t], CODES[c], PLAN_IDS[p], round(rec[t, c, p], 2), round(-contra[t, c, p], 2)))
    df = pd.DataFrame(rows, columns=["month", "country_code", "plan_id", "subscription_revenue_recognized_usd", "refund_chargeback_reversals_usd"])
    deferred = [rb[: t + 1, t + 1:].sum() for t in range(NM)]
    dr = pd.DataFrame({"month": MSTR, "deferred_revenue_closing_usd": np.round(deferred, 2)})
    return df, dr
