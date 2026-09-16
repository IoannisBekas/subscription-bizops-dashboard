# Strategy & BizOps dataset for a subscription business (synthetic)
_A modelled consumer subscription business in the AI-companion category. Price points follow a live site checked on 15-Sep-2026; all volumes, costs and outcomes are simulated. This is not any company's reported data._

## At a glance
Actuals Jan-2024 to Aug-2026 (daily / monthly), Budget FY2025 & FY2026, Forecast Sep-Dec 2026. Reporting currency USD; revenue is ex-VAT.
362,430 paying subscribers, 1,050,539 billing transactions, 122,560 support tickets.
Aug-2026: 175,203 active subscribers, subscription ARR $13.2M, net-revenue run-rate $22.0M.
Net revenue: FY2024 $3.5M, FY2025 $9.3M, Jan-Aug 2026 $12.0M.

## What is taken from the category vs what is modelled
Taken from live pricing pages: 1 / 3 / 12-month plans at 13.99 / 8.99 / 3.99 per month (list 13.99; 35% and 70% off), 100 tokens a month with Premium, token top-ups, token uses (images, voice messages, voice calls, private content packs, video, custom characters), Visa / Mastercard / crypto (BTC, ETH, USDC, LTC), a free tier and a localised French site.
Modelled: earlier price books, token pack prices (store is behind login), traffic, conversion, retention, channels and campaigns, processors (generic names), GPU providers (generic), costs, headcount, budgets and experiments.

## How the tables fit together
Star schema: fact_* tables join to dim_* on *_id / date / month. fact_subscribers is the customer table (join on subscriber_id from support tickets).
Everything reconciles: subscribers = first payments in marketing and funnel; MRR bridge opening + movements = closing; GPU clusters = usage compute cost; every refund has a ticket; P&L revenue ties to the revenue and recognised-revenue tables.
Excel workbook holds every table except the three largest (fact_subscribers, fact_revenue_daily, fact_support_tickets) which are CSV only: load them with Power Query / Power BI.
PnL_View and Budget_vs_Actual are live formulas (SUMIFS over fact_pnl_monthly): edit the data and they recalculate.

## Key definitions
MRR: ex-tax recurring revenue at month-end, 3- and 12-month plans normalised to monthly, EUR / GBP converted at the month's FX. ARR = MRR x 12 (tokens excluded).
Churn types: Voluntary (did not renew), Involuntary (renewal payment failed after retries), Refund, Chargeback. Win-backs are reactivations.
Revenue: subscription revenue recognised straight-line over the service period (deferred for 3M / 12M plans); token packs recognised at purchase.
CAC: acquisition spend / first payments (blended includes organic). LTV: cumulative net revenue per original cohort member (fact_cohort_retention).

## Suggested dashboard pages
1. Executive summary: ARR, net revenue, EBITDA margin, active subs, MRR waterfall (fact_mrr_bridge_monthly, fact_kpi_monthly).
2. P&L and budget vs actual: where is FY26 beating / missing plan and why? (PnL_View, Budget_vs_Actual, fact_pnl_monthly).
3. Growth engine: CAC, payback and LTV:CAC by channel and campaign; what happened to paid social in Q1-26? (fact_marketing_daily, fact_cohort_retention).
4. Pricing: what did the 70%-off annual price book do to conversion, plan mix, MRR per sub and cash? (dim_price_book, fact_experiment_daily, fact_subscribers).
5. Retention: cohort heatmap, M1 step-change after Jul-25, annual renewal wave from Jun-26 (cohort_retention_matrix).
6. Monetisation: token attach, ARPPU and whale concentration (fact_subscribers.token_spend_segment, fact_revenue_daily).
7. Compute efficiency: GPU cost per sub and by modality, free-tier cost, cluster mix (fact_usage_daily, fact_gpu_daily).
8. Operations: payment declines and dunning by processor, chargeback ratio, support SLA / backlog / CSAT (fact_payments_monthly, fact_support_tickets).
Use dim_business_events to annotate charts (launches, price changes, outages, compliance).

## Tables
- `fact_subscribers` | 362,430 rows | CSV only | One row per paying subscriber (first payment Oct-23 to Aug-26). Oct-Dec 2023 cohorts include only those still active on 1-Jan-24; revenue columns cover 2024-01 onwards.
- `fact_mrr_bridge_monthly` | 14,165 rows | CSV + Excel | MRR waterfall: opening MRR, new, win-back, expansion, contraction, FX, churn by type, closing MRR, plus subscriber counts.
- `fact_cohort_retention` | 39,672 rows | CSV + Excel | Cohort survival and cumulative net revenue (LTV curves). Cohorts from 2024-01.
- `cohort_retention_matrix` | 32 rows | CSV + Excel | Wide retention heatmap (share of cohort active at month-end, M0..M31). All channels and plans.
- `cohort_ltv_matrix` | 32 rows | CSV + Excel | Wide cumulative net revenue per original subscriber (USD), M0..M31.
- `fact_revenue_daily` | 162,700 rows | CSV only | Every billing event aggregated daily: new, renewal, win-back, token packs, refunds, chargebacks. Gross, tax, net, fees.
- `fact_revenue_monthly` | 11,315 rows | CSV + Excel | Monthly roll-up of fact_revenue_daily (cash / billings view).
- `fact_recognized_revenue_monthly` | 1,632 rows | CSV + Excel | Subscription revenue recognised straight-line over the service period (3- and 12-month plans are deferred).
- `fact_deferred_revenue` | 32 rows | CSV + Excel | Closing deferred subscription revenue balance (prepaid plans not yet recognised).
- `fact_payments_monthly` | 1,555 rows | CSV + Excel | Payment operations: attempts, first-attempt declines, dunning recoveries, approvals, refunds, chargebacks, fees.
- `fact_marketing_daily` | 25,716 rows | CSV + Excel | Spend, impressions, clicks, free sign-ups, first payments and first-payment revenue by campaign. CRM rows carry win-backs.
- `fact_funnel_daily` | 49,674 rows | CSV + Excel | Acquisition funnel: sessions, UK age checks, sign-ups, activation, paywall views, checkouts, new paid subscribers.
- `fact_experiment_daily` | 2,056 rows | CSV + Excel | A/B test results in long format (additive counts and sums; compute rates as metric / exposure).
- `fact_usage_daily` | 7,450 rows | CSV + Excel | Product engagement and cost to serve: active users, units, tokens consumed, GPU and content cost, latency, errors.
- `fact_gpu_daily` | 6,996 rows | CSV + Excel | GPU spend by cluster and workload; sums to compute_cost_usd in fact_usage_daily.
- `fact_support_tickets` | 122,560 rows | CSV only | Customer support tickets with SLA, first response, resolution, CSAT. Every refund transaction has a matching ticket.
- `fact_headcount_monthly` | 320 rows | CSV + Excel | Headcount, hires, exits and fully-loaded payroll cost.
- `fact_pnl_monthly` | 1,260 rows | CSV + Excel | P&L in long format. Actual Jan-24 to Aug-26, Budget FY25 & FY26, Forecast Sep-Dec 26 (8+4). Costs are negative.
- `fact_kpi_monthly` | 32 rows | CSV + Excel | Executive KPI scorecard: one row per month with ~50 headline metrics derived from the other tables.
- `fin_model_drivers` | 19 rows | CSV + Excel | Driver sheet for a FY2027 plan: FY25 actual, FY26 YTD actual and downside / base / upside scenario values.
- `dim_date` | 1,096 rows | CSV + Excel | Calendar 2024-01-01 to 2026-12-31 with promo events and actual / forecast flag.
- `dim_country` | 17 rows | CSV + Excel | Markets with pricing currency, VAT / sales-tax rate (prices are tax-inclusive) and tier.
- `dim_channel` | 10 rows | CSV + Excel | Acquisition channels and their cost model.
- `dim_campaign` | 34 rows | CSV + Excel | Campaigns with channel, geo target and flight dates.
- `dim_plan` | 3 rows | CSV + Excel | Subscription plans with current prices (category benchmark, Sep-2026).
- `dim_price_book` | 3 rows | CSV + Excel | Price history per plan. PB3 matches the live site; PB1 / PB2 are modelled.
- `dim_token_pack` | 6 rows | CSV + Excel | Token top-up packs (illustrative: the token store is behind login).
- `dim_payment_method` | 7 rows | CSV + Excel | Card and crypto methods (Visa, Mastercard and crypto are accepted on the site).
- `dim_processor` | 4 rows | CSV + Excel | Payment processors with fee schedule and modelled decline / recovery rates (generic names).
- `dim_feature` | 8 rows | CSV + Excel | Token-consuming product features with token price per unit and launch date.
- `dim_gpu_cluster` | 5 rows | CSV + Excel | Inference clusters (generic providers) with GPU type, pricing model and hourly rate.
- `dim_fx_monthly` | 32 rows | CSV + Excel | Monthly average FX used to convert EUR / GBP charges to USD (approximate).
- `dim_experiment` | 10 rows | CSV + Excel | A/B test register: hypothesis, primary metric, dates, decision.
- `dim_business_events` | 34 rows | CSV + Excel | Timeline of launches, pricing changes, ops and compliance events, for annotating charts.
- `dim_pnl_line` | 21 rows | CSV + Excel | P&L line items with section and display order.

## Regenerate

`python generator/build.py --export` (Python 3.10+, numpy, pandas, xlsxwriter; seeded, fully reproducible).
