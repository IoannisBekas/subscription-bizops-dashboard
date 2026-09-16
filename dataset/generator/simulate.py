"""Subscriber-level simulation: one row per paying subscriber, simulated month by month."""
import numpy as np
import pandas as pd
from config import (MONTHS, NM, HZ, COUNTRIES, CHANNELS, TIER, EUROPE, FX, PERIOD, TOKEN_PACKS, PROCESSORS,
                    ACQ_C_SHARE, LEGACY, CB_MULT, interp)

PRICES = np.array([[12.99, 9.99, 5.99], [13.99, 9.99, 5.99], [13.99, 8.99, 3.99]])   # per month, by era
MIX_P3, MIX_P12 = np.array([0.18, 0.18, 0.16]), np.array([0.20, 0.22, 0.36])
BR = np.array([  # voluntary renewal probability by plan and renewal number (1..12+)
    [0.60, 0.75, 0.81, 0.84, 0.86, 0.88, 0.89, 0.90, 0.90, 0.91, 0.91, 0.92],
    [0.52, 0.68, 0.74, 0.76, 0.77, 0.78, 0.78, 0.78, 0.78, 0.78, 0.78, 0.78],
    [0.40, 0.58, 0.60, 0.60, 0.60, 0.60, 0.60, 0.60, 0.60, 0.60, 0.60, 0.60]])
PACK_TOK, PACK_PRICE = TOKEN_PACKS.tokens.to_numpy(), TOKEN_PACKS.price.to_numpy()
PACK_W = np.array([0.50, 0.25, 0.13, 0.07, 0.035, 0.015])
FEE_PCT, FEE_FIX, CB_FEE = (PROCESSORS[c].to_numpy() for c in ("fee_pct", "fee_fixed_usd", "chargeback_fee_usd"))
DEC_INIT, DEC_REN, RECOV = (PROCESSORS[c].to_numpy() for c in ("initial_decline_rate", "renewal_decline_rate", "dunning_recovery_rate"))
TX_TYPES = ["New subscription", "Renewal", "Reactivation", "Token pack", "Refund - subscription",
            "Refund - token pack", "Chargeback"]
REACT_MULT = {1: 1.3, 2: 1.4, 4: 1.1, 7: 1.2, 8: 1.15, 10: 1.1, 11: 2.0, 12: 1.2}
TOKEN_LAM = interp({0: 0.045, 9: 0.047, 10: 0.062, 14: 0.070, 25: 0.073, 26: 0.085, 31: 0.087})


def era_of(t):
    return 0 if t < 14 else (1 if t < 17 else 2)


def sig(x):
    return 1 / (1 + np.exp(-x))


def choose_plan(rng, era, promo, tier, crypto, device, react=False):
    p3 = MIX_P3[era]
    p12 = MIX_P12[era] + 0.08 * promo + 0.06 * (tier == 2) + 0.10 * crypto + 0.03 * (device == 1) + 0.05 * react
    u = rng.random(len(p12))
    return np.where(u < p12, 2, np.where(u < p12 + p3, 1, 0)).astype(np.int8)


def create_subscribers(cells, dd, rng):
    c = cells[cells.new_subs > 0]
    idx = np.repeat(c.index.to_numpy(), c.new_subs.to_numpy())
    s = cells.loc[idx, ["date", "m", "campaign_id", "channel", "country", "device"]]
    jan = c[c.m == 0]
    legacy = []                                  # Oct-Dec 2023 sign-ups, attributed like January 2024 traffic
    for cm, cnt in LEGACY.items():
        li = rng.choice(jan.index.to_numpy(), cnt, p=(jan.new_subs / jan.new_subs.sum()).to_numpy())
        g = cells.loc[li, ["campaign_id", "channel", "country", "device"]].copy()
        start = pd.Timestamp("2024-01-01") + pd.DateOffset(months=cm)
        g["date"] = start + pd.to_timedelta(rng.integers(0, start.days_in_month, cnt), unit="D")
        g["m"] = cm
        legacy.append(g)
    s = pd.concat([s] + legacy).sample(frac=1, random_state=7)
    s = s.sort_values("date", kind="stable").reset_index(drop=True)
    n = len(s)
    s["promo"] = dd.set_index("date").promo_event.ne("").reindex(s.date, fill_value=False).to_numpy()
    tier = TIER[s.country]
    late = (s.date >= "2026-01-15").to_numpy()                        # 1-click USDC checkout
    cshare = CHANNELS._crypto_share.to_numpy()[s.channel] * np.where(tier == 2, 1.3, 1.0) * np.where(late, 1.25, 1.0)
    crypto = rng.random(n) < cshare
    u = rng.random(n)
    cr = np.where(late[:, None], [[0.28, 0.43, 0.93]], [[0.35, 0.55, 0.90]])       # BTC | ETH | USDC | LTC
    crypto_pm = 3 + (u[:, None] >= cr).sum(1)
    card_pm = np.where(u < 0.64, 0, np.where(u < 0.97, 1, 2))
    s["pm"] = np.where(crypto, crypto_pm, card_pm).astype(np.int8)
    s["crypto"] = crypto
    s["base_proc"] = np.where(crypto, 3, np.where(EUROPE[s.country], 0, 1)).astype(np.int8)
    d = s.date.to_numpy()
    era = np.where(d < np.datetime64("2025-03-01"), 0, np.where(d < np.datetime64("2025-06-01"), 1, 2))
    in_exp = (d >= np.datetime64("2025-04-01")) & (d < np.datetime64("2025-06-01"))
    s["exp_variant"] = np.where(in_exp, np.where(rng.random(n) < 0.5, "B (70% off annual)", "A (57% off annual)"), "")
    era = np.where(s.exp_variant.str.startswith("B"), 2, era)
    s["era"] = era
    s["plan0"] = choose_plan(rng, era, s.promo.to_numpy(), tier, crypto, s.device.to_numpy())
    s["price0"] = PRICES[era, s.plan0]
    s["z"] = rng.normal(0, 0.55, n)                                        # engagement (retention)
    s["w"] = np.exp(0.84 * rng.normal(0, 1, n) + 0.5 * s.z) / 1.48          # spend propensity (whales)
    n_ren = np.where(s.plan0 == 0, np.maximum(-s.m - 1, 0), 0)            # monthly renewals before 2024
    alive = (s.m >= 0) | (rng.random(n) < 0.58 ** n_ren)
    return s[alive].reset_index(drop=True)


def simulate(s, rng):
    N = len(s)
    ctry, chan, dev = s.country.to_numpy(), s.channel.to_numpy(), s.device.to_numpy()
    tier, taxd = TIER[ctry], 1 + COUNTRIES.tax_rate.to_numpy()[ctry]
    FXC = np.stack([FX[c] for c in COUNTRIES.pricing_currency])[ctry]      # (N, NM)
    cohort, day0 = s.m.to_numpy(), s.date.dt.day.to_numpy()
    crypto, pm, base_proc = s.crypto.to_numpy(), s.pm.to_numpy(), s.base_proc.to_numpy()
    card, u_proc, z, w = ~crypto, rng.random(N), s.z.to_numpy(), s.w.to_numpy()
    onb, promo = (s.date >= "2025-07-15").to_numpy(), s.promo.to_numpy()
    tokm = CHANNELS._token_mult.to_numpy()[chan] * np.array([1.1, 0.9, 0.6])[tier]
    static = CHANNELS._quality.to_numpy()[chan] + np.array([-0.05, 0.08, 0.0])[dev] + np.array([0.06, 0.0, -0.18])[tier] + z
    active, plan, mrr = np.zeros(N, bool), s.plan0.to_numpy().astype(np.int8), np.zeros(N)
    k, next_ren = np.zeros(N, np.int16), np.full(N, -1, np.int16)
    churn_m, first_churn, ctype = np.full(N, -1, np.int16), np.full(N, -1, np.int16), np.zeros(N, np.int8)
    blocked, reacts, react_flag = np.zeros(N, bool), np.zeros(N, np.int16), np.zeros(N, bool)
    cb_pend, cb_gross, cb_net = np.full(N, -1, np.int16), np.zeros(N), np.zeros(N)
    first_net = np.zeros(N)
    rec, contra = np.zeros((HZ, len(COUNTRIES), 3)), np.zeros((HZ, len(COUNTRIES), 3))
    plan0, mact, rec_by_bill = plan.copy(), np.zeros(N, np.int16), np.zeros((NM, HZ))
    TX, REN, BRIDGE, COH, ACTIVE = [], [], [], [], []
    leg = np.nonzero(cohort < 0)[0]                  # 2023 base still active on 1-Jan-2024
    active[leg], mrr[leg] = True, s.price0.to_numpy()[leg]
    k[leg] = np.where(plan[leg] == 0, -cohort[leg], 1)
    next_ren[leg] = np.where(plan[leg] == 0, 0, cohort[leg] + PERIOD[plan[leg]])
    pre = leg[plan[leg] > 0]                         # prepaid in 2023 -> opening deferred revenue
    amt = mrr[pre] / taxd[pre] * FXC[pre, 0]
    for off in range(12):
        sel = next_ren[pre] > off
        np.add.at(rec, (off, ctry[pre[sel]], plan[pre[sel]]), amt[sel])
        rec_by_bill[0, off] += amt[sel].sum()

    def tx(t, idx, typ, day, gross, net, fee, proc, plan_or_pack):
        TX.append(pd.DataFrame({"t": t, "sid": idx, "type": typ, "day": day, "gross_usd": gross, "net_usd": net,
                                "fee_usd": fee, "proc": proc, "item": plan_or_pack}))

    def schedule(t, idx, pl, net, refund, cb):
        per = PERIOD[pl]
        for off in range(12):
            m = (per > off) & (~refund | (off == 0)) & (~cb | (off <= 1))
            if m.any():
                np.add.at(rec, (t + off, ctry[idx[m]], pl[m]), net[m] / per[m])
                rec_by_bill[t, t + off] += (net[m] / per[m]).sum()
        np.add.at(contra, (t, ctry[idx[refund]], pl[refund]), net[refund] / per[refund])
        n_rec = np.minimum(per[cb], 2)
        np.add.at(contra, (t + 1, ctry[idx[cb]], pl[cb]), net[cb] / per[cb] * n_rec)

    for t in range(NM):
        fxt, fxp = FXC[:, t], FXC[:, max(t - 1, 0)]
        S = np.where(active, mrr / taxd * fxp, 0.0)
        was, prev = active.copy(), mrr.copy()
        share_c = 0.0 if t < 25 else ACQ_C_SHARE.get(t, 0.70)
        proc = np.where(card & (u_proc < share_c), 2, base_proc).astype(np.int8)
        dim, era, cal_m = MONTHS[t].days_in_month, era_of(t), MONTHS[t].month
        p_cb = np.where(proc == 2, 0.0035, 0.0095 if t < 15 else 0.0045) * card * CB_MULT[chan]
        mv = {x: np.zeros(N) for x in ("new", "react", "exp", "con", "fx")}
        cash = np.zeros(N)

        # chargebacks raised this month (on last month's payments)
        cbi = np.nonzero(cb_pend == t)[0]
        tx(t, cbi, 6, rng.integers(1, dim + 1, len(cbi)), -cb_gross[cbi], -cb_net[cbi], CB_FEE[proc[cbi]], proc[cbi], plan[cbi])
        cash[cbi] -= cb_net[cbi]
        hit = cbi[active[cbi]]
        active[hit], churn_m[hit], ctype[hit] = False, t, 4
        blocked[cbi], cb_pend[cbi] = True, -1

        # renewals
        i = np.nonzero(active & (next_ren == t))[0]
        pl, kk = plan[i], k[i]
        x = np.log(BR[pl, np.minimum(kk - 1, 11)] / (1 - BR[pl, np.minimum(kk - 1, 11)])) + static[i]
        x += np.where(onb[i], np.where(kk == 1, 0.25, 0.08), 0) - 0.12 * (promo[i] & (kk == 1))
        x -= np.where(crypto[i], np.where(pl == 0, 0.45, 0.30), 0) + 0.15 * react_flag[i] + 0.05 * (cal_m == 1)
        if t in (16, 17):
            x -= 0.20 * ((pl == 0) & (mrr[i] < 13.5))                          # price-increase shock
        stay = rng.random(len(i)) < sig(x)
        declined = card[i] & stay & (rng.random(len(i)) < DEC_REN[proc[i]] + 0.01 * (cal_m == 1))
        recovered = declined & (rng.random(len(i)) < RECOV[proc[i]])
        fail = declined & ~recovered
        REN.append(pd.DataFrame({"t": t, "sid": i[stay], "proc": proc[i[stay]], "declined": declined[stay],
                                 "recovered": recovered[stay]}))
        for grp, code in ((i[~stay], 1), (i[fail], 2)):
            active[grp], churn_m[grp], ctype[grp] = False, t, code
        r = i[stay & ~fail]
        pl, u = plan[r], rng.random(len(r))
        p112 = (0.012 if era < 2 else 0.035) + 0.035 * (cal_m == 11)
        p312 = 0.05 if era < 2 else 0.08
        newpl = pl.copy()
        newpl[(pl == 0) & (u < p112)] = 2
        newpl[(pl == 0) & (u >= p112) & (u < p112 + 0.010)] = 1
        newpl[(pl == 1) & (u < p312)] = 2
        newpl[(pl == 1) & (u >= p312) & (u < p312 + 0.06)] = 0
        newpl[(pl == 2) & (k[r] == 1) & (u < 0.12)] = 0
        sw = newpl != pl
        price = np.where(sw, PRICES[era, newpl], mrr[r])
        if t >= 16:
            price = np.where((newpl == 0) & ~sw & (price < 13.5), 13.99, price)   # legacy 12.99 -> 13.99
        plan[r], mrr[r], k[r], next_ren[r] = newpl, price, k[r] + 1, t + PERIOD[newpl]
        gross = price * PERIOD[newpl] * fxt[r]
        net = gross / taxd[r]
        tx(t, r, 1, np.minimum(day0[r], dim), gross, net, gross * FEE_PCT[proc[r]] + FEE_FIX[proc[r]], proc[r], newpl)
        cash[r] += net
        rr = (newpl == 0) & (rng.random(len(r)) < (0.012 if t < 15 else 0.008))
        cbf = ~rr & (rng.random(len(r)) < p_cb[r])
        schedule(t, r, newpl, net, rr, cbf)
        q = r[rr]
        tx(t, q, 4, np.minimum(day0[q] + rng.integers(1, 15, len(q)), dim), -gross[rr], -net[rr], 0.0, proc[q], newpl[rr])
        cash[q] -= net[rr]
        active[q], churn_m[q], ctype[q] = False, t, 3
        cb_pend[r[cbf]], cb_gross[r[cbf]], cb_net[r[cbf]] = t + 1, gross[cbf], net[cbf]

        # new subscribers
        n = np.nonzero(cohort == t)[0]
        pl = plan[n]
        active[n], mrr[n], k[n], next_ren[n] = True, s.price0.to_numpy()[n], 1, t + PERIOD[pl]
        gross = mrr[n] * PERIOD[pl] * fxt[n]
        net = gross / taxd[n]
        tx(t, n, 0, day0[n], gross, net, gross * FEE_PCT[proc[n]] + FEE_FIX[proc[n]], proc[n], pl)
        cash[n] += net
        first_net[n] = net
        mv["new"][n] = mrr[n] / taxd[n] * fxt[n]
        ref = rng.random(len(n)) < np.array([0.028, 0.032, 0.045])[pl] * np.where(tier[n] == 2, 0.75, 1.0)
        cbf = ~ref & (rng.random(len(n)) < p_cb[n])
        schedule(t, n, pl, net, ref, cbf)
        q = n[ref]
        tx(t, q, 4, np.minimum(day0[q] + rng.integers(1, 15, len(q)), dim), -gross[ref], -net[ref], 0.0, proc[q], pl[ref])
        cash[q] -= net[ref]
        active[q], churn_m[q], ctype[q], blocked[q] = False, t, 3, True
        cb_pend[n[cbf]], cb_gross[n[cbf]], cb_net[n[cbf]] = t + 1, gross[cbf], net[cbf]

        # win-backs / reactivations
        el = np.nonzero(~active & ~blocked & (churn_m >= 0) & (churn_m < t))[0]
        g, ty = t - churn_m[el], ctype[el]
        h = np.where(g <= 3, 0.020, np.where(g <= 12, 0.008, 0.004))
        h = np.where((ty == 2) & (g == 1), 0.10, np.where((ty == 2) & (g <= 3), 0.03, h)) * np.where(ty == 3, 0.5, 1.0)
        h *= REACT_MULT.get(cal_m, 1.0) * (1.4 if t == 31 else 1.0) * (1.35 if t >= 13 else 1.0) * (1.5 if t >= 20 else 1.0)
        rx = el[rng.random(len(el)) < h * np.exp(0.3 * z[el])]
        pl = choose_plan(rng, np.full(len(rx), era), np.zeros(len(rx), bool), tier[rx], crypto[rx], dev[rx], react=True)
        plan[rx], mrr[rx], active[rx], k[rx], next_ren[rx] = pl, PRICES[era, pl], True, 2, t + PERIOD[pl]
        first_churn[rx] = np.where(first_churn[rx] < 0, churn_m[rx], first_churn[rx])
        churn_m[rx], ctype[rx], reacts[rx], react_flag[rx] = -1, 0, reacts[rx] + 1, True
        gross = mrr[rx] * PERIOD[pl] * fxt[rx]
        net = gross / taxd[rx]
        tx(t, rx, 2, rng.integers(1, dim + 1, len(rx)), gross, net, gross * FEE_PCT[proc[rx]] + FEE_FIX[proc[rx]], proc[rx], pl)
        cash[rx] += net
        mv["react"][rx] = mrr[rx] / taxd[rx] * fxt[rx]
        cbf = rng.random(len(rx)) < p_cb[rx]
        schedule(t, rx, pl, net, np.zeros(len(rx), bool), cbf)
        cb_pend[rx[cbf]], cb_gross[rx[cbf]], cb_net[rx[cbf]] = t + 1, gross[cbf], net[cbf]

        # MRR movements for retained subscribers
        ret = was & active
        mv["fx"][ret] = prev[ret] / taxd[ret] * (fxt[ret] - fxp[ret])
        dlt = np.where(ret, (mrr - prev) / taxd * fxt, 0.0)
        mv["exp"], mv["con"] = np.maximum(dlt, 0), np.minimum(dlt, 0)
        E = np.where(active, mrr / taxd * fxt, 0.0)

        # token packs (premium only)
        pool = np.nonzero(active)[0]
        lam = TOKEN_LAM[t] * (1.1 if cal_m in (2, 11, 12) else 1.0)
        pbuy = 1 - np.exp(-lam * w[pool] ** 0.85 * tokm[pool] * np.array([1.0, 0.95, 0.85])[plan[pool]] * np.where(cohort[pool] == t, 1.2, 1.0))
        b = pool[rng.random(len(pool)) < pbuy]
        b = np.repeat(b, 1 + rng.poisson(0.12 * np.minimum(w[b], 6)))
        pw = PACK_W * (w[b, None] ** 0.30) ** np.arange(6)
        if t < 9:
            pw[:, 5] = 0
        pk = (rng.random(len(b))[:, None] > np.cumsum(pw / pw.sum(1, keepdims=True), 1)).sum(1).clip(0, 5)
        gross = PACK_PRICE[pk] * fxt[b]
        net = gross / taxd[b]
        tx(t, b, 3, rng.integers(1, dim + 1, len(b)), gross, net, gross * FEE_PCT[proc[b]] + FEE_FIX[proc[b]], proc[b], pk)
        np.add.at(cash, b, net)
        tr = rng.random(len(b)) < 0.015
        tx(t, b[tr], 5, rng.integers(1, dim + 1, tr.sum()), -gross[tr], -net[tr], 0.0, proc[b[tr]], pk[tr])
        np.add.at(cash, b[tr], -net[tr])

        # aggregate this month: MRR bridge (month x country x channel x plan) and cohorts
        churned = was & ~active
        new_ref = (cohort == t) & (ctype == 3) & ~active
        tc = np.nonzero(was | active | (cohort == t) | (cash != 0))[0]
        d = {"t": t, "country": ctry[tc], "channel": chan[tc], "plan": plan[tc],
             "subs_start": was[tc], "new_subs": cohort[tc] == t, "reactivated_subs": mv["react"][tc] > 0,
             "expansion_subs": dlt[tc] > 0, "contraction_subs": dlt[tc] < 0, "subs_end": active[tc],
             "mrr_start": S[tc], "mrr_new": mv["new"][tc], "mrr_reactivation": mv["react"][tc],
             "mrr_expansion": mv["exp"][tc], "mrr_contraction": mv["con"][tc], "mrr_fx": mv["fx"][tc]}
        for code, nm in ((1, "voluntary"), (2, "involuntary"), (3, "refund"), (4, "chargeback")):
            sel = churned & (ctype == code)
            d[f"churned_{nm}_subs"] = (sel | (new_ref if code == 3 else False))[tc]
            d[f"mrr_churn_{nm}"] = (np.where(sel, -S, 0.0) - (np.where(new_ref, mv["new"], 0.0) if code == 3 else 0))[tc]
        d["mrr_end"] = E[tc]
        BRIDGE.append(pd.DataFrame(d).groupby(["t", "country", "channel", "plan"], as_index=False).sum())
        COH.append(pd.DataFrame({"cohort": cohort[tc], "t": t, "channel": chan[tc], "plan0": plan0[tc],
                                 "tier": tier[tc], "active_end": active[tc], "mrr_end": E[tc], "cash_net": cash[tc]})
                   .groupby(["cohort", "t", "channel", "plan0", "tier"], as_index=False).sum())
        ACTIVE.append(np.nonzero(active)[0].astype(np.int32))
        mact += active

    s["status"] = np.where(active, "Active", "Churned")
    s["current_plan"], s["reactivations"] = plan, reacts
    s["last_churn_m"], s["churn_type"], s["first_churn_m"] = churn_m, ctype, np.where(first_churn >= 0, first_churn, churn_m)
    s["first_payment_net_usd"] = first_net
    s["proc_now"] = np.where(card & (u_proc < 0.70), 2, base_proc)
    s["mrr_end_usd"], s["months_active"] = E, mact
    out = {"tx": pd.concat(TX, ignore_index=True), "bridge": pd.concat(BRIDGE, ignore_index=True),
           "cohort": pd.concat(COH, ignore_index=True), "ren": pd.concat(REN, ignore_index=True),
           "rec": rec, "contra": contra, "rec_by_bill": rec_by_bill, "active_idx": ACTIVE}
    return s, out
