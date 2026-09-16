"""Static dimensions and business parameters for the synthetic Candy AI dataset.

Public facts (checked on candy.ai, Sep 2026): Monthly / 3-Month / 12-Month plans at
13.99 / 8.99 / 3.99 per month (list 13.99, 35% and 70% off), 100 tokens per month
with Premium, token top-ups, Visa / Mastercard / crypto (BTC, ETH, USDC, LTC),
French localisation, EverAI Limited (Malta). Everything else is modelled.
"""
import numpy as np
import pandas as pd

SEED = 42
START = pd.Timestamp("2024-01-01")
ACT_END = pd.Timestamp("2026-08-31")      # last day of actuals
CAL_END = pd.Timestamp("2026-12-31")      # budget / forecast horizon
MONTHS = pd.period_range("2024-01", "2026-08", freq="M")
NM = len(MONTHS)                           # 32 actual months
HZ = 44                                    # months tracked for deferred revenue (to 2027-08)


LEGACY = {-3: 2600, -2: 3200, -1: 3900}    # paid sign-ups Oct-Dec 2023 (only survivors on 1-Jan-24 enter)


def midx(ts):
    ts = pd.Timestamp(ts)
    return (ts.year - 2024) * 12 + ts.month - 1


def mlabel(i):
    """Month label for an index relative to 2024-01 (negative = 2023)."""
    return np.array([str(pd.Period("2024-01", "M") + int(x)) for x in np.atleast_1d(i)])


def interp(anchors, n=NM, log=False):
    """anchors: {month_idx: value} -> array of length n (linear or log-linear)."""
    xs, ys = zip(*sorted(anchors.items()))
    ys = np.log(ys) if log else np.array(ys, float)
    out = np.interp(np.arange(n), xs, ys)
    return np.exp(out) if log else out


# ---- FX: USD per 1 unit of pricing currency (monthly average, approximate) ----
EURUSD = np.array([1.091, 1.079, 1.087, 1.072, 1.081, 1.076, 1.084, 1.101, 1.111, 1.090, 1.063, 1.048,
                   1.035, 1.041, 1.081, 1.123, 1.128, 1.153, 1.168, 1.165, 1.173, 1.163, 1.156, 1.171,
                   1.172, 1.180, 1.162, 1.151, 1.158, 1.166, 1.174, 1.169])
GBPUSD = np.array([1.271, 1.263, 1.271, 1.252, 1.264, 1.271, 1.286, 1.294, 1.322, 1.305, 1.275, 1.265,
                   1.236, 1.253, 1.290, 1.314, 1.337, 1.355, 1.349, 1.343, 1.349, 1.333, 1.316, 1.338,
                   1.346, 1.352, 1.339, 1.331, 1.340, 1.348, 1.354, 1.350])
FX = {"USD": np.ones(NM), "EUR": EURUSD, "GBP": GBPUSD}

# ---- Countries: pricing currency, VAT/sales tax (prices are tax-inclusive), mix weights ----
COUNTRIES = pd.DataFrame([
    ("US", "United States", "North America", "Tier 1", "USD", 0.060, 0.380, 0.330),
    ("GB", "United Kingdom", "Europe", "Tier 1", "GBP", 0.200, 0.085, 0.070),
    ("DE", "Germany", "Europe", "Tier 1", "EUR", 0.190, 0.080, 0.078),
    ("FR", "France", "Europe", "Tier 1", "EUR", 0.200, 0.045, 0.090),
    ("CA", "Canada", "North America", "Tier 1", "USD", 0.130, 0.050, 0.048),
    ("AU", "Australia", "APAC", "Tier 1", "USD", 0.100, 0.040, 0.040),
    ("NL", "Netherlands", "Europe", "Tier 1", "EUR", 0.210, 0.025, 0.025),
    ("CH", "Switzerland", "Europe", "Tier 1", "EUR", 0.081, 0.015, 0.016),
    ("SE", "Sweden", "Europe", "Tier 1", "EUR", 0.250, 0.015, 0.015),
    ("ES", "Spain", "Europe", "Tier 2", "EUR", 0.210, 0.030, 0.033),
    ("IT", "Italy", "Europe", "Tier 2", "EUR", 0.220, 0.030, 0.032),
    ("PL", "Poland", "Europe", "Tier 2", "EUR", 0.230, 0.020, 0.022),
    ("JP", "Japan", "APAC", "Tier 2", "USD", 0.100, 0.015, 0.020),
    ("BR", "Brazil", "LATAM", "Tier 3", "USD", 0.050, 0.030, 0.040),
    ("MX", "Mexico", "LATAM", "Tier 3", "USD", 0.160, 0.025, 0.030),
    ("IN", "India", "APAC", "Tier 3", "USD", 0.180, 0.020, 0.026),
    ("ROW", "Rest of World", "Rest of World", "Tier 3", "USD", 0.050, 0.095, 0.085),
], columns=["country_code", "country", "region", "market_tier", "pricing_currency", "tax_rate", "_w24", "_w26"])
NC = len(COUNTRIES)
CC = {c: i for i, c in enumerate(COUNTRIES.country_code)}
TIER = COUNTRIES.market_tier.map({"Tier 1": 0, "Tier 2": 1, "Tier 3": 2}).to_numpy()
EUROPE = (COUNTRIES.region == "Europe").to_numpy()


def country_weights():
    """(NM, NC) share of new subscribers by country and month."""
    w = np.stack([interp({0: a, 31: b}) for a, b in zip(COUNTRIES._w24, COUNTRIES._w26)], axis=1)
    fr = CC["FR"]
    w[:12, fr] = 0.045                                   # French site launched Jan-2025
    w[12:, fr] = interp({12: 0.075, 31: 0.090})[12:]
    w[midx("2025-08-01"):, CC["GB"]] *= 0.80             # UK age-assurance friction from 25-Jul-2025
    return w / w.sum(1, keepdims=True)


GEO = {
    "Global": list(COUNTRIES.country_code), "NA": ["US", "CA"], "UK": ["GB"], "FR": ["FR"],
    "EU": ["DE", "FR", "NL", "CH", "SE", "ES", "IT", "PL"], "LATAM": ["BR", "MX"],
    "APAC": ["AU", "JP", "IN"], "Tier1": ["US", "GB", "DE", "FR", "CA", "AU", "NL", "CH", "SE"],
    "EU-nonFR": ["DE", "NL", "CH", "SE", "ES", "IT", "PL"],
}

# ---- Acquisition channels ----
CHANNELS = pd.DataFrame([
    ("CH01", "Affiliates", "Paid - Partners", "CPA per first payment", 0.05, 1.00, 0.08),
    ("CH02", "Adult Ad Networks", "Paid - Media", "CPM", -0.12, 0.90, 0.07),
    ("CH03", "Paid Social (X / Reddit)", "Paid - Media", "CPM / CPC", 0.00, 1.00, 0.05),
    ("CH04", "Creator Partnerships", "Paid - Partners", "Flat fee + rev-share", 0.18, 1.60, 0.06),
    ("CH05", "SEO / Content", "Organic", "Content production", 0.10, 1.00, 0.08),
    ("CH06", "Direct / Brand", "Organic", "None", 0.15, 1.10, 0.10),
    ("CH07", "Discord & Community", "Organic", "Community management", 0.22, 1.30, 0.12),
    ("CH08", "Push & Pop Networks", "Paid - Media", "CPM", -0.60, 0.70, 0.04),
    ("CH09", "Crypto Ad Networks", "Paid - Media", "CPM", 0.00, 1.20, 0.55),
    ("CH10", "CRM / Email Win-back", "Retention", "ESP + incentives", 0.00, 1.00, 0.00),
], columns=["channel_id", "channel", "channel_group", "cost_model", "_quality", "_token_mult", "_crypto_share"])
NCH = len(CHANNELS)
CB_MULT = np.array([1.0, 1.3, 1.0, 0.8, 0.8, 0.8, 0.7, 2.2, 1.0, 1.0])   # chargeback propensity by channel
# share of new paid subscribers by channel: anchors at month 0 / 12 / 21 / 31 (CH10 = win-back only)
MIX = {
    "CH01": (0.26, 0.26, 0.25, 0.24), "CH02": (0.17, 0.16, 0.14, 0.13), "CH03": (0.09, 0.11, 0.12, 0.07),
    "CH04": (0.02, 0.04, 0.06, 0.08), "CH05": (0.11, 0.13, 0.16, 0.20), "CH06": (0.13, 0.13, 0.14, 0.16),
    "CH07": (0.06, 0.06, 0.06, 0.06), "CH08": (0.10, 0.07, 0.03, 0.00), "CH09": (0.06, 0.04, 0.04, 0.06),
}


def channel_weights():
    w = np.zeros((NM, NCH))
    for j, cid in enumerate(CHANNELS.channel_id):
        if cid in MIX:
            w[:, j] = interp(dict(zip((0, 12, 21, 31), MIX[cid])))
    w[midx("2025-11-01"):, 7] = 0                          # push & pop sunset after Oct-2025
    w[midx("2026-04-01"):, 2] *= 0.60                      # paid social cut after Q1-26 CAC spike
    return w


# ---- Campaigns: (channel, name, geo, start month idx, end month idx, weight) ----
_CAMPAIGNS = [
    ("CH01", "AFF_Global_CPA", "Global", 0, 31, 3.0), ("CH01", "AFF_NA_Tier1-CPA", "NA", 0, 31, 2.0),
    ("CH01", "AFF_EU_CPA", "EU", 0, 31, 1.5), ("CH01", "AFF_FR_Review-Sites", "FR", 12, 31, 1.0),
    ("CH01", "AFF_LATAM_CPA", "LATAM", 6, 31, 0.8),
    ("CH02", "ADN_NA_Native", "NA", 0, 31, 2.0), ("CH02", "ADN_EU_Native", "EU", 0, 31, 1.5),
    ("CH02", "ADN_Global_Banner", "Global", 0, 31, 1.5), ("CH02", "ADN_NA_Video-Preroll", "NA", 10, 31, 1.2),
    ("CH02", "ADN_UK_Native", "UK", 0, 18, 1.0), ("CH02", "ADN_APAC_Banner", "APAC", 8, 31, 0.8),
    ("CH03", "SOC_X_NA_Carousel", "NA", 0, 31, 2.0), ("CH03", "SOC_X_EU_Video", "EU", 3, 31, 1.5),
    ("CH03", "SOC_Reddit_NA_Promoted", "NA", 6, 31, 1.5), ("CH03", "SOC_Reddit_EU_Promoted", "EU", 12, 31, 1.0),
    ("CH03", "SOC_X_UK_Video", "UK", 0, 18, 1.0), ("CH03", "SOC_X_Global_Retargeting", "Global", 0, 31, 0.8),
    ("CH04", "CRE_Tier1_Creator-Collabs", "Tier1", 0, 31, 2.0), ("CH04", "CRE_NA_Podcast-Reads", "NA", 12, 31, 1.0),
    ("CH04", "CRE_EU_Creator-Collabs", "EU", 15, 31, 1.2), ("CH04", "CRE_Global_Signature-Character", "Global", 24, 31, 2.5),
    ("CH05", "SEO_EN_Content-Hubs", "Global", 0, 31, 3.0), ("CH05", "SEO_FR_Localized-Site", "FR", 12, 31, 1.5),
    ("CH05", "SEO_EU_Multilingual-Pages", "EU-nonFR", 20, 31, 1.5),
    ("CH06", "DIR_Brand-Direct", "Global", 0, 31, 1.0),
    ("CH07", "COM_Discord-Server", "Global", 0, 31, 2.0), ("CH07", "COM_Reddit-Community", "Global", 6, 31, 1.0),
    ("CH08", "PSH_Global_Push", "Global", 0, 21, 2.0), ("CH08", "PSH_LATAM_Pop", "LATAM", 0, 21, 1.0),
    ("CH08", "PSH_APAC_Pop", "APAC", 0, 21, 1.0),
    ("CH09", "CRY_Global_Crypto-Display", "Global", 0, 31, 2.0), ("CH09", "CRY_NA_Web3-Native", "NA", 8, 31, 1.0),
    ("CH10", "CRM_Winback-Email", "Global", 13, 31, 1.0), ("CH10", "CRM_Lapsed-Push", "Global", 20, 31, 1.0),
]
CAMPAIGNS = pd.DataFrame(_CAMPAIGNS, columns=["channel_id", "campaign_name", "geo_target", "_s", "_e", "_w"])
CAMPAIGNS.insert(0, "campaign_id", [f"CMP{i + 1:03d}" for i in range(len(CAMPAIGNS))])
CAMPAIGNS["launch_month"] = [str(MONTHS[s]) if s > 0 else "2023-10" for s in CAMPAIGNS._s]
CAMPAIGNS["end_month"] = [str(MONTHS[e]) if e < 31 else "" for e in CAMPAIGNS._e]

# ---- Plans & price book (nominal price identical in USD / EUR / GBP, tax-inclusive) ----
PLANS = pd.DataFrame([
    ("P1M", "1 Month", 1), ("P3M", "3 Months", 3), ("P12M", "12 Months", 12),
], columns=["plan_id", "plan_name", "billing_period_months"])
PERIOD = np.array([1, 3, 12])
PRICE_BOOK = pd.DataFrame([
    ("PB1", "2024-01-01", "2025-02-28", 12.99, 9.99, 5.99),
    ("PB2", "2025-03-01", "2025-05-31", 13.99, 9.99, 5.99),
    ("PB3", "2025-06-01", "", 13.99, 8.99, 3.99),
], columns=["price_book_id", "valid_from", "valid_to", "p1m_per_month", "p3m_per_month", "p12m_per_month"])
PB_START = [pd.Timestamp(x) for x in PRICE_BOOK.valid_from]
EXP_ANNUAL = (pd.Timestamp("2025-04-01"), pd.Timestamp("2025-05-31"))   # 57% vs 70% off test
MONTHLY_PRICE_UPLIFT_RENEWALS = pd.Timestamp("2025-05-01")            # legacy 12.99 -> 13.99

# ---- Token packs (store is login-gated -> illustrative) ----
TOKEN_PACKS = pd.DataFrame([
    ("TP100", 100, 9.99, "2024-01-01"), ("TP275", 275, 24.99, "2024-01-01"),
    ("TP600", 600, 49.99, "2024-01-01"), ("TP1300", 1300, 99.99, "2024-01-01"),
    ("TP2800", 2800, 199.99, "2024-01-01"), ("TP4500", 4500, 299.99, "2024-10-01"),
], columns=["pack_id", "tokens", "price", "available_from"])
TOKEN_PACKS["price_per_100_tokens"] = (TOKEN_PACKS.price / TOKEN_PACKS.tokens * 100).round(2)
TOKEN_PACKS["discount_vs_smallest"] = (1 - TOKEN_PACKS.price_per_100_tokens / TOKEN_PACKS.price_per_100_tokens[0]).round(3)

# ---- Payment methods & processors ----
PAY_METHODS = pd.DataFrame([
    ("PM01", "Visa", "Card"), ("PM02", "Mastercard", "Card"), ("PM03", "Other card", "Card"),
    ("PM04", "Crypto - BTC", "Crypto"), ("PM05", "Crypto - ETH", "Crypto"),
    ("PM06", "Crypto - USDC", "Crypto"), ("PM07", "Crypto - LTC", "Crypto"),
], columns=["payment_method_id", "payment_method", "method_type"])
PROCESSORS = pd.DataFrame([
    ("ACQ_A", "Acquirer A (EU high-risk)", "Card", "2024-01", 0.055, 0.35, 25.0, 0.140, 0.120, 0.30),
    ("ACQ_B", "Acquirer B (US high-risk)", "Card", "2024-01", 0.060, 0.30, 25.0, 0.160, 0.140, 0.32),
    ("ACQ_C", "Acquirer C (network tokens + smart retries)", "Card", "2026-02", 0.049, 0.30, 20.0, 0.100, 0.070, 0.52),
    ("CRYPTO_GW", "Crypto gateway", "Crypto", "2024-01", 0.015, 0.00, 0.0, 0.040, 0.000, 0.00),
], columns=["processor_id", "processor", "method_type", "live_from", "fee_pct", "fee_fixed_usd",
            "chargeback_fee_usd", "initial_decline_rate", "renewal_decline_rate", "dunning_recovery_rate"])
ACQ_C_SHARE = {midx("2026-02-01"): 0.30, midx("2026-03-01"): 0.55}   # 0.70 from Apr-2026

# ---- Product features: token price and modelled unit compute cost ----
FEATURES = pd.DataFrame([
    ("F01", "Chat message", "LLM text", "message", 0.0, "2024-01-01"),
    ("F02", "Voice message", "TTS", "message", 0.2, "2024-01-01"),
    ("F03", "Voice call", "Speech-to-speech", "minute", 3.0, "2024-06-03"),
    ("F04", "Image generation", "Image diffusion", "image", 2.0, "2024-01-01"),
    ("F05", "Video generation", "Video diffusion", "clip", 10.0, "2024-11-04"),
    ("F06", "Custom character creation", "Image diffusion + LLM", "character", 2.0, "2024-01-01"),
    ("F07", "Private content (MPC) unlock", "Content (no GPU)", "pack", 30.0, "2024-03-04"),
    ("F08", "Live Action session", "Content (no GPU)", "session", 15.0, "2026-03-02"),
], columns=["feature_id", "feature", "modality", "unit", "tokens_per_unit", "launch_date"])
