"""Headcount, P&L (actual / budget / forecast) and the business-events timeline."""
import numpy as np
import pandas as pd
from config import NM, MONTHS, interp

MSTR = [str(m) for m in MONTHS]
ALL_M = [str(m) for m in pd.period_range("2024-01", "2026-12", freq="M")]
DEPTS = pd.DataFrame([  # department, cost group, start HC, Aug-26 HC, monthly fully-loaded cost per FTE (2024)
    ("Engineering", "R&D", 5, 13, 7200), ("ML / AI", "R&D", 2, 6, 10200), ("Product & Design", "R&D", 1, 4, 6400),
    ("Data & Analytics", "R&D", 1, 3, 6000), ("Growth & Marketing", "Sales & Marketing", 2, 6, 5500),
    ("Customer Support", "Support & Trust", 1, 4, 3000), ("Trust & Safety", "Support & Trust", 1, 4, 3200),
    ("Finance & Strategy", "G&A", 1, 3, 6400), ("People, Legal & Admin", "G&A", 1, 2, 5100), ("Leadership", "G&A", 2, 3, 13000),
], columns=["department", "cost_group", "hc0", "hc1", "cost"])
LINES = [  # line_id, line item, section
    ("R1", "Subscription revenue (recognised)", "Revenue"), ("R2", "Token pack revenue", "Revenue"),
    ("R3", "Refunds & chargebacks", "Revenue"),
    ("C1", "GPU inference", "COGS"), ("C2", "Hosting, storage & CDN", "COGS"), ("C3", "Payment processing fees", "COGS"),
    ("C4", "Chargeback fees", "COGS"), ("C5", "Content & creator costs", "COGS"), ("C6", "Third-party AI APIs & licences", "COGS"),
    ("O1", "Performance marketing (media)", "Opex - S&M"), ("O2", "Affiliate & creator partnerships", "Opex - S&M"),
    ("O3", "SEO, community & CRM", "Opex - S&M"), ("O4", "Brand & content marketing", "Opex - S&M"),
    ("O5", "Payroll - R&D", "Opex - R&D"), ("O6", "Payroll - Support & Trust", "Opex - G&A"),
    ("O7", "Payroll - Sales & Marketing", "Opex - S&M"), ("O8", "Payroll - G&A", "Opex - G&A"),
    ("O9", "Outsourced support (BPO)", "Opex - G&A"), ("O10", "Age assurance & compliance", "Opex - G&A"),
    ("O11", "Software & tools", "Opex - G&A"), ("O12", "Office, travel & other G&A", "Opex - G&A"),
]
LINE_NAME = {i: n for i, n, _ in LINES}
SEASON = {1: 1.01, 2: 1.02, 11: 1.06, 12: 1.03}


def fact_headcount(rng):
    rows = []
    for _, d in DEPTS.iterrows():
        target = np.round(interp({0: d.hc0, 12: d.hc0 + 0.45 * (d.hc1 - d.hc0), 31: d.hc1}))
        prev = d.hc0
        for t in range(NM):
            exits = rng.binomial(int(prev), 0.012)
            hires = max(0, int(target[t] - prev + exits))
            hc = prev + hires - exits
            raise_ = 1.03 ** (MONTHS[t].year - 2024)
            rows.append((MSTR[t], d.department, d.cost_group, hc, hires, exits, round(hc * d.cost * raise_ * rng.uniform(0.98, 1.02), 2)))
            prev = hc
    return pd.DataFrame(rows, columns=["month", "department", "cost_group", "headcount_eom", "hires", "exits", "fully_loaded_cost_usd"])


def pnl_actual(rec, contra, tx, usage, mkt, tickets, funnel, hc):
    a = {k: np.zeros(NM) for k, _, _ in LINES}
    a["R1"] = rec[:NM].sum(axis=(1, 2))
    by = tx.groupby(["t", "type"])
    net, fee = by.net_usd.sum().unstack(fill_value=0).reindex(range(NM), fill_value=0), by.fee_usd.sum().unstack(fill_value=0).reindex(range(NM), fill_value=0)
    a["R2"] = net[3].to_numpy()
    a["R3"] = -contra[:NM].sum(axis=(1, 2)) + net[5].to_numpy()
    nr = a["R1"] + a["R2"] + a["R3"]
    mon = lambda df, col: df.assign(m=pd.to_datetime(df[df.columns[0]]).dt.to_period("M").astype(str)).groupby("m")[col].sum().reindex(MSTR, fill_value=0).to_numpy()
    a["C1"] = -mon(usage, "compute_cost_usd")
    a["C2"] = -(0.030 * nr + interp({0: 12000, 31: 30000}))
    a["C3"] = -(fee[[0, 1, 2, 3]].sum(1).to_numpy())
    a["C4"] = -fee[6].to_numpy()
    shorts = np.where(np.arange(NM) >= 20, interp({20: 30000, 26: 55000, 31: 60000}), 0)
    a["C5"] = -(mon(usage, "content_cost_usd") + shorts + 0.04 * a["R2"])
    a["C6"] = -(0.012 * nr + 4000)
    ch = mkt.groupby([pd.to_datetime(mkt.date).dt.to_period("M").astype(str), "channel_id"]).spend_usd.sum().unstack(fill_value=0).reindex(MSTR, fill_value=0)
    g = lambda ids: ch.reindex(columns=ids, fill_value=0).sum(1).to_numpy()
    a["O1"], a["O2"], a["O3"] = -g(["CH02", "CH03", "CH08", "CH09"]), -g(["CH01", "CH04"]), -g(["CH05", "CH07", "CH10"])
    a["O4"] = -interp({0: 5000, 31: 25000})
    pay = hc.groupby(["month", "cost_group"]).fully_loaded_cost_usd.sum().unstack(fill_value=0).reindex(MSTR)
    a["O5"], a["O6"], a["O7"], a["O8"] = (-pay[c].to_numpy() for c in ("R&D", "Support & Trust", "Sales & Marketing", "G&A"))
    tk = tickets.assign(m=pd.to_datetime(tickets.created_at).dt.to_period("M").astype(str)).groupby("m").size().reindex(MSTR, fill_value=0).to_numpy()
    a["O9"] = -tk * np.where(np.arange(NM) >= 14, 2.70, 3.10)
    a["O10"] = -(mon(funnel, "age_checks_started") * 0.30 + interp({0: 6000, 31: 15000}))
    a["O11"], a["O12"] = -interp({0: 12000, 31: 45000}), -interp({0: 8000, 31: 22000})
    return a


def pnl_budget(act):
    """FY25 budget set in Dec-24 and FY26 budget set in Dec-25 from a smooth driver plan."""
    b = {k: np.full(36, np.nan) for k, _, _ in LINES}
    plan = {2025: dict(g_sub=0.047, g_tok=0.058, gpu=0.21, proc=0.076, cbf=0.004, cont=0.03, hc_add=0.030, g_mkt=0.035),
            2026: dict(g_sub=0.040, g_tok=0.046, gpu=0.15, proc=0.068, cbf=0.0025, cont=0.065, hc_add=0.022, g_mkt=0.025)}
    for fy, p in plan.items():
        t0 = (fy - 2024) * 12 - 1                         # December of the prior year
        for j in range(12):
            t, cal = t0 + 1 + j, j + 1
            s = SEASON.get(cal, 1.0)
            r1 = act["R1"][t0] * (1 + p["g_sub"]) ** (j + 1) * s
            r2 = act["R2"][t0] * (1 + p["g_tok"]) ** (j + 1) * s
            r3 = -0.015 * (r1 + r2)
            nr = r1 + r2 + r3
            b["R1"][t], b["R2"][t], b["R3"][t] = r1, r2, r3
            b["C1"][t], b["C2"][t], b["C3"][t] = -p["gpu"] * nr, -0.055 * nr, -p["proc"] * nr
            b["C4"][t], b["C5"][t], b["C6"][t] = -p["cbf"] * nr, -p["cont"] * nr, -0.016 * nr
            for k in ("O1", "O2", "O3"):                 # marketing plan grows off the December run-rate
                b[k][t] = np.mean(act[k][t0 - 2: t0 + 1]) * (1 + p["g_mkt"]) ** (j + 1) * (s if k != "O3" else 1.0)
            b["O4"][t] = act["O4"][t0] * 1.02 ** (j + 1)
            for k in ("O5", "O6", "O7", "O8"):
                b[k][t] = act[k][t0] * (1 + p["hc_add"]) ** (j + 1) * (1.03 if fy > 2024 else 1)
            b["O9"][t] = act["O9"][t0] * (1.02 ** (j + 1))
            b["O10"][t] = act["O10"][t0] * (1.35 if fy == 2025 and cal >= 7 else 1.0) * 1.01 ** (j + 1)
            b["O11"][t], b["O12"][t] = act["O11"][t0] * 1.03 ** (j + 1), act["O12"][t0] * 1.015 ** (j + 1)
    return b


def pnl_forecast(act):
    """8+4 forecast: Sep-Dec 2026 from Aug-26 exit rates, trailing ratios and planned spend."""
    f = {k: np.full(36, np.nan) for k, _, _ in LINES}
    last = NM - 1
    nr_last = act["R1"][last] + act["R2"][last] + act["R3"][last]
    for j, t in enumerate(range(NM, 36)):
        cal = 9 + j
        s = SEASON.get(cal, 1.0)
        r1 = act["R1"][last] * (1.017 ** (j + 1)) * s * (0.985 if cal in (9, 10) else 1.0)   # annual renewal wave drag
        r2 = act["R2"][last] * (1.022 ** (j + 1)) * s
        r3 = act["R3"][last] / (act["R1"][last] + act["R2"][last]) * (r1 + r2)
        nr = r1 + r2 + r3
        f["R1"][t], f["R2"][t], f["R3"][t] = r1, r2, r3
        for k in ("C1", "C2", "C3", "C4", "C5", "C6"):
            ratio = sum(act[k][last - i] for i in range(3)) / sum(act["R1"][last - i] + act["R2"][last - i] + act["R3"][last - i] for i in range(3))
            f[k][t] = ratio * nr
        for k in ("O1", "O2", "O3"):
            f[k][t] = act[k][last - 2: last + 1].mean() * (1.25 if cal == 11 else 1.04)
        for k in ("O4", "O5", "O6", "O7", "O8", "O10", "O11", "O12"):
            f[k][t] = act[k][last] * 1.01 ** (j + 1)
        f["O9"][t] = act["O9"][last] * (1.2 if cal == 11 else 1.02)
    return f


def fact_pnl(act, bud, fc):
    rows = []
    for scen, data, rng_ in (("Actual", act, range(NM)), ("Budget", bud, range(12, 36)), ("Forecast", fc, range(NM, 36))):
        for lid, name, sec in LINES:
            for t in rng_:
                v = data[lid][t]
                if not np.isnan(v):
                    rows.append((ALL_M[t], scen, lid, name, sec, round(float(v), 2)))
    return pd.DataFrame(rows, columns=["month", "scenario", "line_id", "line_item", "section", "amount_usd"])


EVENTS = [
    ("2024-03-04", "Product", "My Private Content (MPC) packs launched", "Token sink; adds content cost"),
    ("2024-04-01", "Growth", "Paywall after 10 free messages (EXP01 shipped)", "Sign-up to paid conversion +6%"),
    ("2024-06-03", "Product", "Voice calls (beta) launched", "New token sink; speech GPU load"),
    ("2024-10-01", "Monetisation", "4,500-token anchor pack added (EXP02 shipped)", "Token average order value up"),
    ("2024-11-04", "Product", "Video generation launched (image-to-video)", "Token revenue step-up; GPU cost up"),
    ("2024-11-04", "Infra", "GPU capacity crunch after video launch (to 15-Dec)", "Image/video p95 latency and error rate spike; tech tickets"),
    ("2025-01-06", "Market", "French localised site launched", "France share of new subs rises"),
    ("2025-02-03", "Retention", "CRM win-back email programme launched", "Reactivations up"),
    ("2025-03-01", "Pricing", "Monthly plan 12.99 -> 13.99 for new subscribers (EXP03)", "Monthly ARPU up"),
    ("2025-03-01", "Ops", "Support BPO vendor change", "Lower first-response time and cost per ticket"),
    ("2025-04-01", "Pricing", "Annual discount test 57% vs 70% off starts (EXP04)", "Half of traffic sees 3.99/mo annual"),
    ("2025-04-07", "Infra", "Video model v2", "Cost per video clip -32%"),
    ("2025-04-14", "Ops", "Self-serve cancellation in account settings", "Cancellation tickets and chargebacks fall"),
    ("2025-05-01", "Pricing", "Legacy monthly subscribers move to 13.99 at renewal", "Expansion MRR spike, short-lived churn bump"),
    ("2025-05-05", "Infra", "Distilled image model", "Cost per image -26%"),
    ("2025-06-01", "Pricing", "New price book: 70% off annual, 35% off quarterly", "Annual mix jumps; MRR per sub down, cash up"),
    ("2025-06-02", "Infra", "LLM batching and speech optimisations", "Chat and voice unit cost down"),
    ("2025-07-15", "Retention", "Onboarding voice preview + memory recap (EXP05)", "Month-1 retention up about 5pp"),
    ("2025-07-25", "Compliance", "UK Online Safety Act age assurance live", "UK sign-ups down; age-check costs"),
    ("2025-09-01", "Ops", "Live chat support launched", "Channel mix shift; faster first response"),
    ("2025-09-15", "Content", "Episodic video series launched", "Content production cost starts"),
    ("2025-10-31", "Marketing", "Push & pop networks sunset (lowest LTV:CAC)", "Lower volume, better cohort quality"),
    ("2025-11-10", "Unit economics", "Free message cap 50 -> 30 per day (EXP06)", "Free-tier GPU cost down about 30%"),
    ("2025-11-17", "Infra", "Prefix/KV caching and video model v3", "Chat and video unit cost down"),
    ("2025-12-31", "Infra", "A100 reserved cluster retired", "LLM moves to on-demand for January"),
    ("2026-01-01", "Marketing", "Paid social CPM inflation and ad-account restrictions (Q1)", "Paid social CAC above $55"),
    ("2026-01-12", "Marketing", "Signature creator character campaign launched", "Creator channel volume up"),
    ("2026-01-15", "Payments", "One-click USDC checkout (EXP07)", "Crypto share of new subs up"),
    ("2026-02-01", "Payments", "Acquirer C migration (network tokens + smart retries)", "Renewal declines and involuntary churn down"),
    ("2026-02-02", "Infra", "H100 1-yr reserved cluster (Cloud C) live", "Lower GPU $/hour"),
    ("2026-03-02", "Product", "Live Action sessions launched", "Token sink; content cost"),
    ("2026-04-01", "Marketing", "Paid social budget cut 40%, reallocated to SEO & creators", "Blended CAC down"),
    ("2026-06-01", "Risk", "First renewals of 70%-off annual cohorts begin", "Annual renewal wave: watch churn Jun-26 onward"),
    ("2026-08-20", "Promo", "Back to School 70% OFF sale (to 13-Sep)", "Volume spike into September"),
]


def dim_events():
    return pd.DataFrame(EVENTS, columns=["event_date", "category", "event", "expected_impact"])
