"""Calendar, promotions and the daily acquisition grid (date x campaign x country x device)."""
import numpy as np
import pandas as pd
from config import (START, ACT_END, CAL_END, MONTHS, NM, COUNTRIES, CHANNELS, CAMPAIGNS, GEO, CC, TIER,
                    country_weights, channel_weights, interp, midx)

PROMOS = [  # name, start, end, volume multiplier
    ("New Year Sale", "2024-01-01", "2024-01-06", 1.30), ("Valentine's Sale", "2024-02-07", "2024-02-15", 1.40),
    ("Summer Sale", "2024-07-01", "2024-07-10", 1.20), ("Halloween Sale", "2024-10-27", "2024-11-01", 1.20),
    ("Black Friday / Cyber Monday", "2024-11-22", "2024-12-02", 1.75), ("New Year Sale", "2024-12-26", "2025-01-06", 1.30),
    ("Valentine's Sale", "2025-02-07", "2025-02-15", 1.40), ("Spring Sale", "2025-04-18", "2025-04-27", 1.20),
    ("Summer Sale", "2025-07-01", "2025-07-10", 1.25), ("Back to School Sale", "2025-08-22", "2025-09-07", 1.20),
    ("Halloween Sale", "2025-10-27", "2025-11-01", 1.25), ("Black Friday / Cyber Monday", "2025-11-21", "2025-12-02", 1.85),
    ("New Year Sale", "2025-12-26", "2026-01-06", 1.30), ("Valentine's Sale", "2026-02-06", "2026-02-15", 1.45),
    ("Spring Sale", "2026-04-17", "2026-04-26", 1.20), ("Summer Sale", "2026-07-01", "2026-07-10", 1.25),
    ("Back to School Sale", "2026-08-20", "2026-09-13", 1.40), ("Halloween Sale", "2026-10-27", "2026-11-01", 1.25),
    ("Black Friday / Cyber Monday", "2026-11-20", "2026-12-01", 1.85), ("New Year Sale", "2026-12-26", "2026-12-31", 1.30),
]
DEVICES = ["Mobile web", "Desktop web", "Tablet web"]
WEEKDAY = np.array([0.95, 0.95, 0.97, 0.98, 1.03, 1.08, 1.06])      # Mon..Sun
# conversion (sign-up -> first payment) multipliers by channel
CH_CVR = np.array([1.10, 0.80, 0.90, 1.35, 1.00, 1.60, 1.50, 0.55, 1.00, 1.00])


def build_dim_date():
    d = pd.DataFrame({"date": pd.date_range(START, CAL_END, freq="D")})
    d["year"] = d.date.dt.year
    d["quarter"] = "Q" + d.date.dt.quarter.astype(str)
    d["year_quarter"] = d.year.astype(str) + "-" + d.quarter
    d["month"] = d.date.dt.to_period("M").astype(str)
    d["month_name"] = d.date.dt.strftime("%b")
    d["iso_week"] = d.date.dt.isocalendar().week.astype(int)
    d["week_start"] = (d.date - pd.to_timedelta(d.date.dt.weekday, unit="D")).dt.date
    d["weekday"] = d.date.dt.strftime("%a")
    d["is_weekend"] = d.date.dt.weekday >= 5
    d["day_of_month"] = d.date.dt.day
    d["days_in_month"] = d.date.dt.days_in_month
    d["promo_event"] = ""
    d["promo_volume_multiplier"] = 1.0
    for name, s, e, mult in PROMOS:
        m = d.date.between(s, e)
        d.loc[m, "promo_event"] = name
        d.loc[m, "promo_volume_multiplier"] = mult
    d["is_actual"] = d.date <= ACT_END
    d["data_scenario"] = np.where(d.is_actual, "Actual", "Forecast")
    return d


def daily_expected(dd, rng):
    """Expected new paid subscribers per actual day."""
    act = dd[dd.is_actual].copy()
    m = (act.year.to_numpy() - 2024) * 12 + act.date.dt.month.to_numpy() - 1
    trend = interp({0: 4800, 11: 7800, 23: 13800, 31: 18000}, log=True) / 30.4
    shock = np.ones(NM)
    shock[midx("2025-11-01")] = 0.97                  # push & pop sunset
    shock[midx("2026-04-01"):midx("2026-06-01")] = 0.95   # paid social cut, before SEO / creators absorb it
    noise = np.exp(rng.normal(0, 0.05, len(act)))
    e = trend[m] * shock[m] * WEEKDAY[act.date.dt.weekday] * act.promo_volume_multiplier.to_numpy() * noise
    return act.date.to_numpy(), m, e


def month_campaign_country_matrix():
    """For each month: probability over (campaign, country) of a new subscriber (rows sum to 1)."""
    cw, chw = country_weights(), channel_weights()
    camp = CAMPAIGNS[CAMPAIGNS.channel_id != "CH10"].reset_index()
    geo = np.zeros((len(camp), len(COUNTRIES)))
    for i, g in enumerate(camp.geo_target):
        geo[i, [CC[c] for c in GEO[g]]] = 1
    ch_idx = camp.channel_id.str[2:].astype(int).to_numpy() - 1
    out = []
    for m in range(NM):
        act = ((camp._s <= m) & (camp._e >= m)).to_numpy()
        elig = geo * act[:, None] * camp._w.to_numpy()[:, None]          # (K, C)
        q = np.zeros_like(elig)
        for c in range(len(COUNTRIES)):
            ch_avail = np.zeros(len(CHANNELS))
            np.add.at(ch_avail, ch_idx, elig[:, c] > 0)
            pj = chw[m] * (ch_avail > 0)
            pj = pj / pj.sum()
            for j in np.nonzero(pj)[0]:
                sel = (ch_idx == j) & (elig[:, c] > 0)
                q[sel, c] = cw[m, c] * pj[j] * elig[sel, c] / elig[sel, c].sum()
        out.append(q)
    return camp, ch_idx, out


def conversion_rate(dates, m, country, device, channel):
    base = interp({0: 0.026, 31: 0.031})[m]
    tier_mult = np.array([1.25, 0.95, 0.55])[TIER[country]]
    dev_mult = np.array([0.92, 1.18, 1.0])[device]
    cvr = base * tier_mult * dev_mult * CH_CVR[channel]
    cvr *= np.where(dates >= np.datetime64("2024-04-01"), 1.06, 1.0)     # paywall-timing test shipped
    cvr *= np.where(dates >= np.datetime64("2025-11-10"), 1.03, 1.0)     # free-message cap shipped
    return cvr


def build_cells(dd, rng):
    dates, m_of_day, e_day = daily_expected(dd, rng)
    camp, ch_idx, Q = month_campaign_country_matrix()
    dev_share = np.stack([interp({0: .66, 31: .71}), interp({0: .31, 31: .265}), interp({0: .03, 31: .025})], 1)
    frames = []
    for m in range(NM):
        k, c = np.nonzero(Q[m])
        days = np.nonzero(m_of_day == m)[0]
        nd, nk = len(days), len(k)
        di = np.repeat(days, nk * 3)
        ki = np.tile(np.repeat(k, 3), nd)
        ci = np.tile(np.repeat(c, 3), nd)
        vi = np.tile(np.tile(np.arange(3), nk), nd)
        e = e_day[di] * Q[m][ki, ci] * dev_share[m, vi]
        frames.append(pd.DataFrame({"date": dates[di], "m": m, "k": ki, "country": ci, "device": vi, "exp_subs": e}))
    cells = pd.concat(frames, ignore_index=True)
    cells["channel"] = ch_idx[cells.k]
    cells["campaign_id"] = camp.campaign_id.to_numpy()[cells.k]
    cells["cvr"] = conversion_rate(cells.date.to_numpy(), cells.m.to_numpy(), cells.country.to_numpy(),
                                   cells.device.to_numpy(), cells.channel.to_numpy())
    cells["new_subs"] = rng.poisson(cells.exp_subs)
    cells["signups"] = rng.poisson(cells.exp_subs / cells.cvr)
    return cells
