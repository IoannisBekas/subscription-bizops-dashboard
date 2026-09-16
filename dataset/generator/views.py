"""Formula-driven Excel views (P&L, budget vs actual) and the README content."""
import numpy as np
import pandas as pd
from xlsxwriter.utility import xl_col_to_name as L
from finance import LINES

LINE_ORDER = [  # kind, id / label, member line ids
    ("L", "R1"), ("L", "R2"), ("L", "R3"), ("S", "Net revenue", ["R1", "R2", "R3"]),
    ("L", "C1"), ("L", "C2"), ("L", "C3"), ("L", "C4"), ("L", "C5"), ("L", "C6"),
    ("S", "Total COGS", ["C1", "C2", "C3", "C4", "C5", "C6"]), ("G", "Gross profit"), ("P", "Gross margin %", "Gross profit"),
    ("L", "O1"), ("L", "O2"), ("L", "O3"), ("L", "O4"), ("L", "O5"), ("L", "O6"), ("L", "O7"), ("L", "O8"),
    ("L", "O9"), ("L", "O10"), ("L", "O11"), ("L", "O12"), ("S", "Total opex", [f"O{i}" for i in range(1, 13)]),
    ("E", "EBITDA"), ("P", "EBITDA margin %", "EBITDA"),
]
NAME = {i: n for i, n, _ in LINES}
SECTION = {i: s for i, _, s in LINES}


def _fmts(wb):
    b = {"font_name": "Arial", "font_size": 10}
    return {"title": wb.add_format({**b, "bold": True, "font_size": 14}), "note": wb.add_format({**b, "italic": True, "font_color": "#555555"}),
            "hdr": wb.add_format({**b, "bold": True, "bg_color": "#1F2937", "font_color": "#FFFFFF", "align": "center"}),
            "in": wb.add_format({**b, "font_color": "#0000FF", "num_format": "#,##0;(#,##0);-"}),
            "f": wb.add_format({**b, "num_format": "#,##0;(#,##0);-"}),
            "sub": wb.add_format({**b, "bold": True, "num_format": "#,##0;(#,##0);-", "top": 1}),
            "pct": wb.add_format({**b, "italic": True, "num_format": "0.0%;(0.0%);-"}),
            "lbl": wb.add_format(b), "lbl_b": wb.add_format({**b, "bold": True}), "h2": wb.add_format({**b, "bold": True, "font_size": 12}),
            "wrap": wb.add_format({**b, "text_wrap": True, "valign": "top"})}


def _layout(first_row):
    """Row number (0-based) for each entry in LINE_ORDER."""
    rows, r = {}, first_row
    for item in LINE_ORDER:
        rows[item[1]] = r
        r += 1
    return rows


def _write_block(ws, F, rows, col, values, formula_for):
    """values: dict line_id -> number; formula_for(kind, item) -> (formula, cached value)."""
    for item in LINE_ORDER:
        kind, key = item[0], item[1]
        r = rows[key]
        if kind == "L":
            ws.write_number(r, col, float(values.get(key, 0.0)), F["in"])
        else:
            f, v = formula_for(kind, item, r)
            ws.write_formula(r, col, f, F["pct"] if kind == "P" else F["sub"], v)


def _calc(values):
    out = dict(values)
    out["Net revenue"] = sum(values.get(k, 0) for k in ("R1", "R2", "R3"))
    out["Total COGS"] = sum(values.get(f"C{i}", 0) for i in range(1, 7))
    out["Total opex"] = sum(values.get(f"O{i}", 0) for i in range(1, 13))
    out["Gross profit"] = out["Net revenue"] + out["Total COGS"]
    out["EBITDA"] = out["Gross profit"] + out["Total opex"]
    nr = out["Net revenue"]
    out["Gross margin %"] = out["Gross profit"] / nr if nr else 0
    out["EBITDA margin %"] = out["EBITDA"] / nr if nr else 0
    return out


def _formula(col_letter, rows, cached):
    def f(kind, item, r):
        c = col_letter
        if kind == "S":
            first, last = rows[item[2][0]] + 1, rows[item[2][-1]] + 1
            return f"=SUM({c}{first}:{c}{last})", cached[item[1]]
        if kind == "G":
            return f"={c}{rows['Net revenue'] + 1}+{c}{rows['Total COGS'] + 1}", cached["Gross profit"]
        if kind == "E":
            return f"={c}{rows['Gross profit'] + 1}+{c}{rows['Total opex'] + 1}", cached["EBITDA"]
        return f"=IFERROR({c}{rows[item[2]] + 1}/{c}{rows['Net revenue'] + 1},0)", cached[item[1]]
    return f


def _labels(ws, F, rows):
    for item in LINE_ORDER:
        kind, key = item[0], item[1]
        label = NAME[key] if kind == "L" else key
        ws.write(rows[key], 0, label, F["lbl"] if kind == "L" else F["lbl_b"])
        ws.write(rows[key], 1, SECTION.get(key, ""), F["lbl"])


def pnl_view(wb, pnl):
    ws, F = wb.add_worksheet("PnL_View"), _fmts(wb)
    d = pnl[pnl.scenario.isin(["Actual", "Forecast"])]
    months = sorted(d.month.unique())
    piv = d.pivot_table(index="line_id", columns="month", values="amount_usd", aggfunc="sum")
    ws.write(0, 0, "Candy AI - Monthly P&L (USD)", F["title"])
    ws.write(1, 0, "Actual Jan-2024 to Aug-2026 | Forecast Sep-Dec 2026 (8+4). Blue = data from fact_pnl_monthly, black = formulas. Costs negative.", F["note"])
    ws.write(3, 0, "Line item", F["hdr"])
    ws.write(3, 1, "Section", F["hdr"])
    rows = _layout(5)
    _labels(ws, F, rows)
    for j, m in enumerate(months):
        col = 2 + j
        ws.write(3, col, m, F["hdr"])
        ws.write(4, col, "Forecast" if m > "2026-08" else "Actual", F["note"])
        vals = piv[m].to_dict()
        _write_block(ws, F, rows, col, vals, _formula(L(col), rows, _calc(vals)))
    for k, yr in enumerate(("2024", "2025", "2026")):
        col = 2 + len(months) + k
        ws.write(3, col, f"FY{yr}", F["hdr"])
        ws.write(4, col, "Actual + Forecast" if yr == "2026" else "Actual", F["note"])
        idx = [j for j, m in enumerate(months) if m.startswith(yr)]
        c0, c1 = L(2 + idx[0]), L(2 + idx[-1])
        vals = piv[[m for m in months if m.startswith(yr)]].sum(1).to_dict()
        cached = _calc(vals)
        for item in LINE_ORDER:
            kind, key, r = item[0], item[1], rows[item[1]]
            if kind == "P":
                f, v = _formula(L(col), rows, cached)(kind, item, r)
                ws.write_formula(r, col, f, F["pct"], v)
            else:
                ws.write_formula(r, col, f"=SUM({c0}{r + 1}:{c1}{r + 1})", F["sub"] if kind != "L" else F["f"], cached[key])
    ws.set_column(0, 0, 34)
    ws.set_column(1, 1, 12)
    ws.set_column(2, 2 + len(months) + 3, 12)
    ws.freeze_panes(5, 2)


def bva_view(wb, pnl):
    ws, F = wb.add_worksheet("Budget_vs_Actual"), _fmts(wb)
    ws.write(0, 0, "Candy AI - Budget vs Actual (USD)", F["title"])
    ws.write(1, 0, "SUMIFS over fact_pnl_monthly. Variance = Actual - Budget: positive is favourable (costs are negative).", F["note"])
    heads = ["Line", "Section", "FY25 Actual", "FY25 Budget", "Var", "Var %", "FY26 YTD Actual (Jan-Aug)", "FY26 YTD Budget",
             "Var", "Var %", "FY26 Outlook (Act + Fcst)", "FY26 Budget", "Var", "Var %"]
    for j, h in enumerate(heads):
        ws.write(3, j, h, F["hdr"])
    rows = _layout(4)
    _labels(ws, F, rows)
    src = "fact_pnl_monthly!"
    blocks = [  # (actual col, budget col, actual criteria, budget criteria, pandas filters)
        (2, 3, [("Actual", 2025, None)], [("Budget", 2025, None)]),
        (6, 7, [("Actual", 2026, 8)], [("Budget", 2026, 8)]),
        (10, 11, [("Actual", 2026, None), ("Forecast", 2026, None)], [("Budget", 2026, None)]),
    ]

    def sumifs(key_cell, crit):
        parts = []
        for scen, yr, mmax in crit:
            s = f'SUMIFS({src}$F:$F,{src}$C:$C,{key_cell},{src}$B:$B,"{scen}",{src}$G:$G,{yr}'
            parts.append(s + (f',{src}$H:$H,"<={mmax}")' if mmax else ")"))
        return "=" + "+".join(parts)

    def pvals(crit):
        tot = pd.Series(0.0, index=[i for i, _, _ in LINES])
        for scen, yr, mmax in crit:
            x = pnl[(pnl.scenario == scen) & (pnl.year == yr) & ((pnl.month_num <= mmax) if mmax else True)]
            tot = tot.add(x.groupby("line_id").amount_usd.sum(), fill_value=0)
        return tot.to_dict()

    for ca, cb, crit_a, crit_b in blocks:
        for c, crit in ((ca, crit_a), (cb, crit_b)):
            vals = pvals(crit)
            cached = _calc(vals)
            for item in LINE_ORDER:
                kind, key, r = item[0], item[1], rows[item[1]]
                if kind == "L":
                    ws.write_formula(r, c, sumifs(f'"{key}"', crit), F["f"], vals.get(key, 0))
                else:
                    f, v = _formula(L(c), rows, cached)(kind, item, r)
                    ws.write_formula(r, c, f, F["pct"] if kind == "P" else F["sub"], v)
        va, vb = _calc(pvals(crit_a)), _calc(pvals(crit_b))
        for item in LINE_ORDER:
            key, r = item[1], rows[item[1]]
            a, b = va.get(key, 0), vb.get(key, 0)
            if item[0] == "P":
                ws.write_formula(r, cb + 1, f"={L(ca)}{r + 1}-{L(cb)}{r + 1}", F["pct"], a - b)
                continue
            ws.write_formula(r, cb + 1, f"={L(ca)}{r + 1}-{L(cb)}{r + 1}", F["f"], a - b)
            ws.write_formula(r, cb + 2, f"=IFERROR({L(cb + 1)}{r + 1}/ABS({L(cb)}{r + 1}),0)", F["pct"], (a - b) / abs(b) if b else 0)
    ws.set_column(0, 0, 34)
    ws.set_column(1, 1, 12)
    ws.set_column(2, 13, 15)
    ws.freeze_panes(4, 2)


def headline(T):
    k = T["fact_kpi_monthly"].set_index("month")
    p = T["fact_pnl_monthly"]
    fy = lambda y: p[(p.scenario == "Actual") & (p.year == y) & (p.section == "Revenue")].amount_usd.sum()
    return {
        "subs": len(T["fact_subscribers"]), "tx": int(T["fact_revenue_daily"].transactions.sum()),
        "active": int(k.loc["2026-08", "active_subscribers_eom"]), "arr": k.loc["2026-08", "arr_eom_usd"] / 1e6,
        "rev24": fy(2024) / 1e6, "rev25": fy(2025) / 1e6, "rev26": fy(2026) / 1e6,
        "run": k.loc["2026-08", "net_revenue_usd"] * 12 / 1e6, "tickets": len(T["fact_support_tickets"]),
    }


def readme_lines(T, tables):
    h = headline(T)
    L_ = [("title", "Candy AI - Strategy & BizOps dataset (synthetic)"),
          ("note", "Modelled on candy.ai's public business model as checked on 15-Sep-2026. All volumes, costs and outcomes are simulated: this is not real company data."),
          ("", ""), ("h2", "At a glance"),
          ("", f"Actuals Jan-2024 to Aug-2026 (daily / monthly), Budget FY2025 & FY2026, Forecast Sep-Dec 2026. Reporting currency USD; revenue is ex-VAT."),
          ("", f"{h['subs']:,} paying subscribers, {h['tx']:,} billing transactions, {h['tickets']:,} support tickets."),
          ("", f"Aug-2026: {h['active']:,} active subscribers, subscription ARR ${h['arr']:.1f}M, net-revenue run-rate ${h['run']:.1f}M."),
          ("", f"Net revenue: FY2024 ${h['rev24']:.1f}M, FY2025 ${h['rev25']:.1f}M, Jan-Aug 2026 ${h['rev26']:.1f}M."),
          ("", ""), ("h2", "What comes from the live site vs what is modelled"),
          ("", "From candy.ai: 1 / 3 / 12-month plans at 13.99 / 8.99 / 3.99 per month (list 13.99; 35% and 70% off), 100 tokens a month with Premium, token top-ups, "
               "token uses (images, voice messages, voice calls, private content packs, video, custom characters), Visa / Mastercard / crypto (BTC, ETH, USDC, LTC), "
               "free trial tier, French site, charges shown as EverAI (Malta)."),
          ("", "Modelled: earlier price books, token pack prices (store is behind login), traffic, conversion, retention, channels and campaigns, processors "
               "(generic names), GPU providers (generic), costs, headcount, budgets and experiments."),
          ("", ""), ("h2", "How the tables fit together"),
          ("", "Star schema: fact_* tables join to dim_* on *_id / date / month. fact_subscribers is the customer table (join on subscriber_id from support tickets)."),
          ("", "Everything reconciles: subscribers = first payments in marketing and funnel; MRR bridge opening + movements = closing; GPU clusters = usage compute cost; "
               "every refund has a ticket; P&L revenue ties to the revenue and recognised-revenue tables."),
          ("", "Excel workbook holds every table except the three largest (fact_subscribers, fact_revenue_daily, fact_support_tickets) which are CSV only: "
               "load them with Power Query / Power BI."),
          ("", "PnL_View and Budget_vs_Actual are live formulas (SUMIFS over fact_pnl_monthly): edit the data and they recalculate."),
          ("", ""), ("h2", "Key definitions"),
          ("", "MRR: ex-tax recurring revenue at month-end, 3- and 12-month plans normalised to monthly, EUR / GBP converted at the month's FX. ARR = MRR x 12 (tokens excluded)."),
          ("", "Churn types: Voluntary (did not renew), Involuntary (renewal payment failed after retries), Refund, Chargeback. Win-backs are reactivations."),
          ("", "Revenue: subscription revenue recognised straight-line over the service period (deferred for 3M / 12M plans); token packs recognised at purchase."),
          ("", "CAC: acquisition spend / first payments (blended includes organic). LTV: cumulative net revenue per original cohort member (fact_cohort_retention)."),
          ("", ""), ("h2", "Suggested dashboard pages"),
          ("", "1. Executive summary: ARR, net revenue, EBITDA margin, active subs, MRR waterfall (fact_mrr_bridge_monthly, fact_kpi_monthly)."),
          ("", "2. P&L and budget vs actual: where is FY26 beating / missing plan and why? (PnL_View, Budget_vs_Actual, fact_pnl_monthly)."),
          ("", "3. Growth engine: CAC, payback and LTV:CAC by channel and campaign; what happened to paid social in Q1-26? (fact_marketing_daily, fact_cohort_retention)."),
          ("", "4. Pricing: what did the 70%-off annual price book do to conversion, plan mix, MRR per sub and cash? (dim_price_book, fact_experiment_daily, fact_subscribers)."),
          ("", "5. Retention: cohort heatmap, M1 step-change after Jul-25, annual renewal wave from Jun-26 (cohort_retention_matrix)."),
          ("", "6. Monetisation: token attach, ARPPU and whale concentration (fact_subscribers.token_spend_segment, fact_revenue_daily)."),
          ("", "7. Compute efficiency: GPU cost per sub and by modality, free-tier cost, cluster mix (fact_usage_daily, fact_gpu_daily)."),
          ("", "8. Operations: payment declines and dunning by processor, chargeback ratio, support SLA / backlog / CSAT (fact_payments_monthly, fact_support_tickets)."),
          ("", "Use dim_business_events to annotate charts (launches, price changes, outages, compliance)."),
          ("", ""), ("h2", "Tables")]
    for _, r in tables.iterrows():
        L_.append(("", f"{r.table}  |  {r.rows:,} rows  |  {r.available_in}  |  {r.description}"))
    return L_


def readme_sheet(wb, T, tables):
    ws, F = wb.add_worksheet("README"), _fmts(wb)
    ws.set_column(0, 0, 160, F["wrap"])
    for i, (style, text) in enumerate(readme_lines(T, tables)):
        ws.write(i, 0, text, F.get(style, F["wrap"]))
    ws.activate()


def readme_markdown(T, tables):
    out = []
    for style, text in readme_lines(T, tables):
        if style == "title":
            out.append(f"# {text}")
        elif style == "h2":
            out.append(f"\n## {text}")
        elif style == "note":
            out.append(f"_{text}_")
        elif text.startswith("fact_") or text.startswith("dim_") or text.startswith("cohort_") or text.startswith("fin_"):
            out.append(f"- `{text.split('  |  ')[0]}` | " + " | ".join(text.split("  |  ")[1:]))
        elif text:
            out.append(text if not text[:2].rstrip(".").isdigit() else text)
        else:
            out.append("")
    return "\n".join(out).replace("\n\n\n", "\n\n") + "\n"
