"""Write CSVs, the Excel workbook (data sheets + formula-driven views) and the data dictionary."""
import os
import numpy as np
import pandas as pd
from dictionary import TABLES, describe
import views

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_DIR = os.path.join(ROOT, "csv")
XLSX = os.path.join(ROOT, "Candy_AI_BizOps_Dataset.xlsx")
CSV_ONLY = {"fact_subscribers", "fact_revenue_daily", "fact_support_tickets"}
FIRST = ["fact_kpi_monthly", "fin_model_drivers", "fact_pnl_monthly", "fact_mrr_bridge_monthly", "fact_cohort_retention",
         "cohort_retention_matrix", "cohort_ltv_matrix"]
PCT_HINTS = ("rate", "margin", "share", "_pct", "discount", "cvr", "retention", "utilization", "fee_pct")


def dictionary_frames(T):
    tables = pd.DataFrame([(n, TABLES[n][0], TABLES[n][1], len(df), df.shape[1],
                            "CSV only" if n in CSV_ONLY else "CSV + Excel") for n, df in T.items()],
                          columns=["table", "grain", "description", "rows", "columns", "available_in"])
    cols = pd.DataFrame([(n, c, str(df[c].dtype), describe(n, c)) for n, df in T.items() for c in df.columns],
                        columns=["table", "column", "dtype", "description"])
    missing = cols[cols.description == ""]
    if len(missing):
        print("WARNING: columns without description:\n", missing.to_string())
    return tables, cols


def col_format(name, series, F):
    if name.endswith("_usd") or name in ("price", "hourly_rate_usd") or name.startswith("mrr") or name.startswith("p1m") or name.startswith("p3m") or name.startswith("p12m"):
        return F["pct"] if "discount" in name else F["usd"]
    if any(h in name for h in PCT_HINTS) and pd.api.types.is_float_dtype(series):
        return F["pct"]
    if pd.api.types.is_integer_dtype(series):
        return F["int"]
    if pd.api.types.is_float_dtype(series):
        return F["num"]
    return None


def write_table(writer, name, df, F, sheet=None):
    sheet = sheet or name[:31]
    df.to_excel(writer, sheet_name=sheet, index=False, startrow=1, header=False)
    ws = writer.sheets[sheet]
    for j, c in enumerate(df.columns):
        ws.write(0, j, c, F["hdr"])
        sample = df[c].astype(str).head(200)
        width = min(max(len(c), int(sample.str.len().max() if len(sample) else 8)) + 2, 48)
        ws.set_column(j, j, width, col_format(c, df[c], F))
    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, max(len(df), 1), len(df.columns) - 1)
    return ws


def export_all(T):
    os.makedirs(CSV_DIR, exist_ok=True)
    tables, cols = dictionary_frames(T)
    for n, df in T.items():
        df.to_csv(os.path.join(CSV_DIR, f"{n}.csv"), index=False)
    tables.to_csv(os.path.join(CSV_DIR, "_dictionary_tables.csv"), index=False)
    cols.to_csv(os.path.join(CSV_DIR, "_dictionary_columns.csv"), index=False)
    print(f"wrote {len(T) + 2} CSVs to {CSV_DIR}")
    with open(os.path.join(ROOT, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(views.readme_markdown(T, tables))
        fh.write("\n## Regenerate\n\n`python generator/build.py --export` (Python 3.10+, numpy, pandas, xlsxwriter; seeded, fully reproducible).\n")

    with pd.ExcelWriter(XLSX, engine="xlsxwriter", date_format="yyyy-mm-dd", datetime_format="yyyy-mm-dd hh:mm") as w:
        wb = w.book
        wb.formats[0].set_font_name("Arial")
        base = {"font_name": "Arial", "font_size": 10}
        F = {"hdr": wb.add_format({**base, "bold": True, "bg_color": "#1F2937", "font_color": "#FFFFFF", "border": 1}),
             "usd": wb.add_format({**base, "num_format": "#,##0.00;(#,##0.00);-"}),
             "pct": wb.add_format({**base, "num_format": "0.0%"}), "int": wb.add_format({**base, "num_format": "#,##0"}),
             "num": wb.add_format({**base, "num_format": "#,##0.00"}), "txt": wb.add_format(base)}
        views.readme_sheet(wb, T, tables)
        write_table(w, "Dictionary_Tables", tables, F)
        write_table(w, "Dictionary_Columns", cols, F)
        views.pnl_view(wb, T["fact_pnl_monthly"])
        views.bva_view(wb, T["fact_pnl_monthly"])
        order = FIRST + sorted(n for n in T if n not in FIRST and n.startswith("fact_")) + sorted(n for n in T if n.startswith("dim_"))
        for n in order:
            if n in CSV_ONLY:
                continue
            ws = write_table(w, n, T[n], F)
            if n == "cohort_retention_matrix":
                ws.conditional_format(1, 2, len(T[n]), T[n].shape[1] - 1,
                                      {"type": "3_color_scale", "min_color": "#F8696B", "mid_color": "#FFEB84", "max_color": "#63BE7B"})
            if n == "cohort_ltv_matrix":
                ws.conditional_format(1, 2, len(T[n]), T[n].shape[1] - 1,
                                      {"type": "2_color_scale", "min_color": "#FFFFFF", "max_color": "#5B8FF9"})
    print(f"wrote {XLSX}")
