"""Marketing (campaign x day), funnel (country x device x day) and experiment tables."""
import numpy as np
import pandas as pd
from config import NM, CHANNELS, CAMPAIGNS, COUNTRIES, TIER, interp, midx
from acquisition import DEVICES

CHIDS = CHANNELS.channel_id.to_numpy()
CAC = np.zeros((len(CHIDS), NM))                       # target CAC / CPA (USD per first payment)
CAC[0] = interp({0: 22, 12: 23.5, 24: 25, 31: 25})
CAC[1] = interp({0: 18, 12: 20, 31: 22})
CAC[2] = np.r_[interp({0: 27, 12: 31, 23: 34}, n=24), [48, 50, 46, 37, 35, 34, 34, 34]]
CAC[3] = interp({0: 40, 12: 36, 31: 32})
CAC[7] = interp({0: 17, 21: 21})
CAC[8] = interp({0: 30, 12: 31, 31: 32})
SEO_DAILY, COMMUNITY_DAILY = interp({0: 450, 12: 700, 31: 1000}), interp({0: 150, 31: 300})
CRM_DAILY = interp({13: 250, 31: 700})
SIGNUPS_PER_CLICK = np.array([0.14, 0.09, 0.11, 0.16, 0.08, 0.20, 0.18, 0.05, 0.10, 0.0])
CTR = np.array([np.nan, 0.006, 0.009, 0.012, 0.035, np.nan, np.nan, 0.018, 0.005, np.nan])


def _month(dates):
    d = pd.DatetimeIndex(dates)
    return ((d.year - 2024) * 12 + d.month - 1).to_numpy()


def fact_marketing_daily(cells, s, tx, rng):
    g = cells.groupby(["date", "campaign_id", "channel"], as_index=False)[["exp_subs", "signups", "new_subs"]].sum()
    fp = s.groupby(["date", "campaign_id"]).first_payment_net_usd.sum().rename("fp")
    g = g.merge(fp.reset_index(), on=["date", "campaign_id"], how="left").fillna({"fp": 0})
    m, ch = _month(g.date), g.channel.to_numpy()
    noise = np.exp(rng.normal(0, 0.15, len(g)))
    spend = np.zeros(len(g))
    media = np.isin(ch, [1, 2, 7, 8])
    spend[media] = (g.exp_subs * CAC[ch, m] * noise)[media]
    spend[ch == 0] = (g.new_subs * CAC[0, m])[ch == 0]
    cre = ch == 3                                       # creators: monthly fee paid on the 1st and 15th
    budget = (g.exp_subs * CAC[3, m]).where(cre, 0).groupby([g.campaign_id, m]).transform("sum")
    day = pd.DatetimeIndex(g.date).day
    spend[cre] = np.where(np.isin(day, [1, 15]), budget * 0.5, 0)[cre]
    for c, daily in ((4, SEO_DAILY), (6, COMMUNITY_DAILY)):
        sel = ch == c
        w = CAMPAIGNS.set_index("campaign_id")._w.reindex(g.campaign_id).to_numpy()
        wsum = pd.Series(np.where(sel, w, 0)).groupby([g.date]).transform("sum").to_numpy()
        spend[sel] = (daily[m] * w / np.where(wsum > 0, wsum, 1) * np.exp(rng.normal(0, 0.08, len(g))))[sel]
    clicks = np.where(SIGNUPS_PER_CLICK[ch] > 0, g.signups / np.where(SIGNUPS_PER_CLICK[ch] > 0, SIGNUPS_PER_CLICK[ch], 1)
                      * np.exp(rng.normal(0, 0.10, len(g))), 0)
    ctr = CTR[ch] * np.where((ch == 2) & (m >= 24) & (m <= 26), 0.75, 1.0)
    out = pd.DataFrame({"date": pd.to_datetime(g.date).dt.date, "campaign_id": g.campaign_id, "channel_id": CHIDS[ch],
                        "spend_usd": spend.round(2), "impressions": np.round(clicks / ctr), "clicks": np.round(clicks),
                        "free_signups": g.signups, "new_paid_subscribers": g.new_subs, "reactivated_subscribers": 0,
                        "first_payment_net_revenue_usd": g.fp.round(2)})
    # CRM win-back campaigns get the reactivations
    rx = tx[tx.type == 2].groupby("date").size()
    rx = rx[_month(rx.index) >= 13]
    crm = []
    for d, n in rx.items():
        t = _month([d])[0]
        n_push = rng.binomial(n, 0.4) if t >= 20 else 0
        for cid, k in (("CMP033", n - n_push), ("CMP034", n_push)):
            if k or (cid == "CMP034" and t >= 20):
                share = 1.0 if t < 20 else (0.6 if cid == "CMP033" else 0.4)
                sends = k / 0.004 * np.exp(rng.normal(0, 0.1))
                crm.append((pd.Timestamp(d).date(), cid, "CH10", round(CRM_DAILY[t] * share + 2.5 * k, 2),
                            round(sends), round(sends * 0.03), 0, 0, k, 0.0))
    out = pd.concat([out, pd.DataFrame(crm, columns=out.columns)], ignore_index=True)
    out.loc[out.channel_id.isin(["CH01", "CH06", "CH07"]), "impressions"] = np.nan
    return out.sort_values(["date", "campaign_id"]).reset_index(drop=True)


def fact_funnel_daily(cells, rng):
    g = cells.groupby(["date", "country", "device"], as_index=False)[["signups", "new_subs"]].sum()
    m, tier, dev = _month(g.date), TIER[g.country], g.device.to_numpy()
    su_rate = np.array([0.105, 0.095, 0.075])[tier] * np.array([0.95, 1.10, 1.0])[dev]
    sessions = np.round(g.signups / su_rate * np.exp(rng.normal(0, 0.06, len(g))))
    act_rate = np.where(pd.to_datetime(g.date) >= "2025-07-15", 0.68, interp({0: 0.60, 18: 0.64})[m])
    paywall = interp({0: 0.36, 31: 0.40})[m]
    completion = np.where(pd.to_datetime(g.date) >= "2026-02-01", 0.62, 0.58) * np.exp(rng.normal(0, 0.05, len(g)))
    checkout = np.maximum(np.round(g.new_subs / completion), g.new_subs)
    gb_av = (g.country.to_numpy() == COUNTRIES.index[COUNTRIES.country_code == "GB"][0]) & (pd.to_datetime(g.date) >= "2025-07-25")
    av_start = np.where(gb_av, np.round(g.signups / 0.78), 0)
    return pd.DataFrame({
        "date": pd.to_datetime(g.date).dt.date, "country_code": COUNTRIES.country_code.to_numpy()[g.country],
        "device": np.array(DEVICES)[dev], "sessions": sessions.astype(int),
        "age_checks_started": av_start.astype(int), "age_checks_passed": np.where(gb_av, g.signups, 0),
        "free_signups": g.signups, "activated_users": rng.binomial(g.signups, act_rate),
        "paywall_viewers": rng.binomial(g.signups, paywall), "checkout_starts": checkout.astype(int),
        "new_paid_subscribers": g.new_subs})


EXPERIMENTS = [  # id, name, area, start, end, metrics (control, treatment rates), decision
    ("EXP01", "Paywall timing: 20 vs 10 free messages", "Growth", "2024-03-04", "2024-03-31", "Shipped B on 2024-04-01"),
    ("EXP02", "Token decoy pack (4,500 tokens) on store", "Monetisation", "2024-09-02", "2024-09-29", "Shipped B on 2024-10-01"),
    ("EXP03", "Monthly price 12.99 vs 13.99", "Pricing", "2025-01-13", "2025-02-09", "Shipped B on 2025-03-01"),
    ("EXP04", "Annual discount 57% vs 70% off", "Pricing", "2025-04-01", "2025-05-31", "Shipped B on 2025-06-01"),
    ("EXP05", "Onboarding voice preview + memory recap", "Retention", "2025-06-16", "2025-07-13", "Shipped B on 2025-07-15"),
    ("EXP06", "Free message cap 50/day vs 30/day", "Unit economics", "2025-10-06", "2025-11-02", "Shipped B on 2025-11-10"),
    ("EXP07", "1-click USDC crypto checkout", "Payments", "2025-12-01", "2026-01-11", "Shipped B on 2026-01-15"),
    ("EXP08", "Smart retries + network tokens (Acquirer C pilot)", "Payments", "2026-01-12", "2026-02-08", "Migrated 70% of card volume by Apr-2026"),
    ("EXP09", "Live Action upsell on paywall", "Monetisation", "2026-03-09", "2026-04-05", "Shipped B on 2026-04-07"),
    ("EXP10", "Back-to-School: 70% vs 75% off annual", "Pricing", "2026-07-13", "2026-08-09", "Kept A (70% off)"),
]
# exposure metric, daily exposed per arm, then (metric, control rate, treatment rate, base metric) per experiment
SPEC = {
    "EXP01": ("paywall_viewers", 5200, [("paid_conversions", 0.078, 0.083, None), ("m1_retained_subs", 0.70, 0.69, "paid_conversions")]),
    "EXP02": ("token_store_visitors", 2400, [("token_buyers", 0.21, 0.205, None), ("token_revenue_usd", 23.5, 26.8, "token_buyers")]),
    "EXP03": ("paywall_viewers", 7400, [("paid_conversions", 0.080, 0.0783, None), ("first_payment_net_usd", 17.9, 18.95, "paid_conversions")]),
    "EXP05": ("new_paid_subscribers", 330, [("m1_retained_subs", 0.665, 0.711, None), ("day7_voice_users", 0.31, 0.44, None)]),
    "EXP06": ("free_active_users", 21000, [("free_messages", 16.0, 11.0, None), ("free_compute_cost_usd", 0.0117, 0.0081, None), ("paid_conversions", 0.0021, 0.00216, None)]),
    "EXP07": ("crypto_checkout_starts", 190, [("checkout_completions", 0.46, 0.56, None)]),
    "EXP08": ("renewal_attempts", 1800, [("first_attempt_declines", 0.125, 0.071, None), ("recovered_by_retry", 0.31, 0.52, "first_attempt_declines")]),
    "EXP09": ("paywall_viewers", 15500, [("paid_conversions", 0.086, 0.0852, None), ("token_buyers_30d", 0.105, 0.115, "paid_conversions")]),
    "EXP10": ("paywall_viewers", 18000, [("paid_conversions", 0.0915, 0.0937, None), ("first_payment_net_usd", 26.4, 25.3, "paid_conversions")]),
}


def experiments(s, funnel, rng):
    rows = []
    for eid, name, area, start, end, _ in EXPERIMENTS:
        days = pd.date_range(start, end, freq="D")
        if eid == "EXP04":            # read straight from the simulated subscribers
            pv = funnel[pd.to_datetime(funnel.date).isin(days)].groupby("date").paywall_viewers.sum()
            sub = s[s.exp_variant != ""]
            for arm, lab in (("A", "Control"), ("B", "Treatment")):
                a = sub[sub.exp_variant.str.startswith(arm)].groupby(sub.date.dt.date)
                for d in days:
                    dd = d.date()
                    rows += [(eid, dd, lab, "paywall_viewers", int(pv.get(dd, 0) / 2))]
                    if dd in a.groups:
                        grp = a.get_group(dd)
                        rows += [(eid, dd, lab, "paid_conversions", len(grp)),
                                 (eid, dd, lab, "annual_plan_conversions", int((grp.plan0 == 2).sum())),
                                 (eid, dd, lab, "first_payment_net_usd", round(grp.first_payment_net_usd.sum(), 2))]
            continue
        base, n, metrics = SPEC[eid]
        for d in days:
            for lab, j in (("Control", 1), ("Treatment", 2)):
                exposed = rng.poisson(n)
                rows.append((eid, d.date(), lab, base, exposed))
                vals = {}
                for met, c, tr, on in metrics:
                    rate = (c, tr)[j - 1]
                    denom = vals.get(on, exposed)
                    if met.endswith("_usd") or met == "free_messages":
                        v = round(denom * rate * np.exp(rng.normal(0, 0.04)), 2)
                    else:
                        v = int(rng.binomial(int(denom), min(rate, 1)))
                    vals[met] = v
                    rows.append((eid, d.date(), lab, met, v))
    fact = pd.DataFrame(rows, columns=["experiment_id", "date", "variant", "metric", "value"])
    dim = pd.DataFrame([(e, n, a, s_, e_, dec) for e, n, a, s_, e_, dec in EXPERIMENTS],
                       columns=["experiment_id", "experiment_name", "area", "start_date", "end_date", "decision"])
    dim["primary_metric"] = dim.experiment_id.map({
        "EXP01": "paid_conversions / paywall_viewers", "EXP02": "token_revenue_usd / token_store_visitors",
        "EXP03": "first_payment_net_usd / paywall_viewers", "EXP04": "first_payment_net_usd / paywall_viewers",
        "EXP05": "m1_retained_subs / new_paid_subscribers", "EXP06": "free_compute_cost_usd / free_active_users",
        "EXP07": "checkout_completions / crypto_checkout_starts", "EXP08": "recovered_by_retry / first_attempt_declines",
        "EXP09": "token_buyers_30d / paid_conversions", "EXP10": "first_payment_net_usd / paywall_viewers"})
    dim["hypothesis"] = dim.experiment_id.map({
        "EXP01": "Showing the paywall earlier converts more users without hurting retention",
        "EXP02": "A large anchor pack lifts average token order value",
        "EXP03": "+$1 on the monthly plan raises revenue per viewer with limited conversion loss",
        "EXP04": "A deeper annual discount lifts conversion and cash collected per viewer",
        "EXP05": "Hearing the companion's voice in onboarding lifts month-1 retention",
        "EXP06": "A tighter free message cap cuts free-tier GPU cost without hurting conversion",
        "EXP07": "One-click USDC reduces crypto checkout abandonment",
        "EXP08": "Network tokens + smart retries reduce involuntary churn",
        "EXP09": "Teasing Live Action on the paywall lifts early token purchases",
        "EXP10": "75% off annual during Back-to-School beats 70% off"})
    return dim, fact
