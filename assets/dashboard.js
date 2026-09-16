/* Builds the briefing: KPI strip, sections, cards and charts from data/dashboard.js */
(function () {
  "use strict";
  const D = window.DASHBOARD_DATA;
  const C = EC.C;
  const fmt = EC.fmt;
  const M = D.monthly;
  const ALL = M.map((d) => d.month);
  const state = { range: "all" };
  const renderers = [];

  const RANGES = { all: ALL.length, "24m": 24, "12m": 12 };
  function idx() {
    const n = RANGES[state.range] || ALL.length;
    return { from: Math.max(0, ALL.length - n) };
  }
  const slice = (arr) => arr.slice(idx().from);
  const col = (key) => slice(M.map((d) => d[key]));
  const months = () => slice(ALL);
  const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const prettyMonth = (m) => MONTH_NAMES[+m.split("-")[1] - 1] + " " + m.split("-")[0];

  /* ---------- scaffolding ---------- */
  function h(tag, attrs, parent) {
    const n = document.createElement(tag);
    for (const k in attrs || {}) {
      if (k === "html") n.innerHTML = attrs[k];
      else if (k === "text") n.textContent = attrs[k];
      else n.setAttribute(k, attrs[k]);
    }
    if (parent) parent.appendChild(n);
    return n;
  }

  function card(grid, o) {
    const c = h("div", { class: "card" + (o.span === "wide" ? " wide" : o.span === "third" ? " third" : "") }, grid);
    h("h3", { text: o.title }, c);
    if (o.sub) h("p", { class: "sub", text: o.sub }, c);
    if (o.legend && o.legend.length) {
      const l = h("div", { class: "legend" }, c);
      o.legend.forEach((it) => {
        const w = h("span", { class: "item" }, l);
        h("span", { class: "swatch" + (it.line ? " line" : ""), style: "background:" + it.color }, w);
        h("span", { text: it.name }, w);
      });
    }
    const chart = h("div", { class: "chart" }, c);
    if (o.note) h("p", { class: "note", html: o.note }, c);
    if (o.table) {
      const btn = h("button", { class: "toggle", type: "button", text: "Show the data" }, c);
      const wrap = h("div", { class: "datatable", style: "display:none" }, c);
      let built = false;
      btn.addEventListener("click", () => {
        const open = wrap.style.display !== "none";
        wrap.style.display = open ? "none" : "block";
        btn.textContent = open ? "Show the data" : "Hide the data";
        if (!built) { buildTable(wrap, o.table()); built = true; }
      });
    }
    return chart;
  }

  function buildTable(wrap, spec) {
    const t = h("table", {}, wrap);
    const thead = h("thead", {}, t);
    const tr = h("tr", {}, thead);
    spec.columns.forEach((cname) => h("th", { text: cname }, tr));
    const tb = h("tbody", {}, t);
    spec.rows.forEach((r) => {
      const row = h("tr", {}, tb);
      r.forEach((v) => h("td", { text: v }, row));
    });
  }

  function tsTable(names, keys, format) {
    return () => ({
      columns: ["Month"].concat(names),
      rows: months().map((m, i) => [prettyMonth(m)].concat(keys.map((k, j) =>
        fmt(typeof k === "function" ? k(i) : col(k)[i], Array.isArray(format) ? format[j] : format))))
    });
  }

  function register(node, draw) { renderers.push({ node: node, draw: draw }); draw(node); }
  function redraw() { renderers.forEach((r) => { r.node.innerHTML = ""; r.draw(r.node); }); }

  function section(id, title, blurb) {
    const s = h("section", { id: id }, document.querySelector("main"));
    const head = h("div", { class: "section-head" }, s);
    h("h2", { text: title }, head);
    if (blurb) h("p", { text: blurb }, head);
    return h("div", { class: "grid" }, s);
  }

  /* ---------- KPI strip ---------- */
  function kpis() {
    const wrap = document.getElementById("kpis");
    D.kpis.forEach((k) => {
      const box = h("div", { class: "kpi" }, wrap);
      h("div", { class: "label", text: k.label }, box);
      const v = k.format === "musd" ? fmt(k.value, "usdM")
        : k.format === "musd12" ? fmt(k.value * 12, "usdM")
          : k.format === "kcount" ? fmt(k.value, "k")
            : k.format === "pct1" ? fmt(k.value, "pct1") : fmt(k.value, "usd2");
      h("div", { class: "value", text: v }, box);
      // percentage-point metrics move on the difference; a ratio flips sign when last year was negative
      const diff = k.format === "pct1" ? k.value - k.prev : k.change;
      const up = diff >= 0;
      const good = k.id === "cac" ? !up : up;
      const chg = h("div", { class: "chg " + (good ? "up" : "down") }, box);
      const pts = k.format === "pct1" ? Math.abs(diff * 100).toFixed(1) + "pp" : Math.abs(k.change * 100).toFixed(0) + "%";
      chg.innerHTML = (up ? "&#9650; +" : "&#9660; -") + pts + " <span>vs a year earlier</span>";
      const sp = h("div", { class: "spark" }, box);
      EC.sparkline(sp, k.spark, good ? C.blue : C.red);
    });
  }

  /* ---------- 1. overview ---------- */
  function overview() {
    const g = section("overview", "The state of play",
      "Two and a half years from launch, the subscription base is compounding and the business has crossed into profit.");

    let node = card(g, {
      span: "wide",
      title: "Revenue has grown six-fold since the start of 2024",
      sub: "Net revenue by month, $'000. Token top-ups now make up two-fifths of the total",
      legend: [{ name: "Subscriptions", color: C.blue }, { name: "Token packs", color: C.cyan }, { name: "Refunds & chargebacks", color: C.red }],
      note: "<b>Source:</b> fact_pnl_monthly, fact_kpi_monthly. Subscription revenue is recognised over the service period, so annual plans are spread across 12 months.",
      table: tsTable(["Subscriptions", "Token packs", "Refunds", "Net revenue"],
        ["subscription_revenue_usd", "token_revenue_usd", "refunds_chargebacks_usd", "net_revenue_usd"], "usd0")
    });
    register(node, (n) => EC.columnChart(n, {
      x: months(), height: 280, yFormat: "usdKs", tipTitle: prettyMonth,
      series: [
        { name: "Subscriptions", color: C.blue, values: col("subscription_revenue_usd") },
        { name: "Token packs", color: C.cyan, values: col("token_revenue_usd") },
        { name: "Refunds & chargebacks", color: C.red, values: col("refunds_chargebacks_usd") }
      ]
    }));

    node = card(g, {
      title: "From burning cash to making it",
      sub: "Gross and EBITDA margin, % of net revenue",
      note: "<b>Source:</b> fact_pnl_monthly. EBITDA is after all operating costs including marketing and payroll. The first quarter of 2024 is left off the chart: on a tiny revenue base the margin was -140%.",
      table: tsTable(["Gross margin", "EBITDA margin"], ["gross_margin", "ebitda_margin"], "pct1")
    });
    register(node, (n) => {
      const skip = Math.max(0, 3 - idx().from);            // hide Jan-Mar 2024 outliers
      EC.lineChart(n, {
        x: months().slice(skip), height: 250, yFormat: "pct0", zero: false, tipTitle: prettyMonth,
        series: [
          { name: "Gross", color: C.blue, values: col("gross_margin").slice(skip), format: "pct1" },
          { name: "EBITDA", color: C.red, values: col("ebitda_margin").slice(skip), format: "pct1" }
        ]
      });
    });

    node = card(g, {
      title: "Where MRR growth comes from",
      sub: "Monthly movements in recurring revenue, $'000",
      legend: [{ name: "New", color: C.add[0] }, { name: "Win-back", color: C.add[1] }, { name: "Expansion", color: C.add[2] },
      { name: "Contraction", color: C.cut[2] }, { name: "Churn", color: C.cut[0] }, { name: "Payment failure", color: C.cut[1] },
      { name: "Net new", color: C.ink, line: true }],
      note: "<b>Source:</b> fact_mrr_bridge_monthly. Contraction is mostly subscribers moving to the cheaper-per-month annual plan; FX is small and excluded from the legend.",
      table: () => ({
        columns: ["Month", "New", "Win-back", "Expansion", "Contraction", "Voluntary churn", "Payment failure", "Net new"],
        rows: slice(D.mrr_movements).map((r) => [prettyMonth(r.month), fmt(r.new, "usd0"), fmt(r.reactivation, "usd0"),
        fmt(r.expansion, "usd0"), fmt(r.contraction, "usd0"), fmt(r.churn_voluntary, "usd0"),
        fmt(r.churn_involuntary, "usd0"), fmt(r.end - r.start, "usd0")])
      })
    });
    register(node, (n) => {
      const mv = slice(D.mrr_movements);
      EC.columnChart(n, {
        x: months(), height: 250, yFormat: "usdKs", tipTitle: prettyMonth,
        series: [
          { name: "New", color: C.add[0], values: mv.map((r) => r.new) },
          { name: "Win-back", color: C.add[1], values: mv.map((r) => r.reactivation) },
          { name: "Expansion", color: C.add[2], values: mv.map((r) => r.expansion) },
          { name: "Contraction", color: C.cut[2], values: mv.map((r) => r.contraction) },
          { name: "Voluntary churn", color: C.cut[0], values: mv.map((r) => r.churn_voluntary) },
          { name: "Payment failure", color: C.cut[1], values: mv.map((r) => r.churn_involuntary) },
          { name: "Refunds & chargebacks", color: C.cut[3], values: mv.map((r) => r.churn_refund + r.churn_chargeback) },
          { name: "FX", color: C.neutral, values: mv.map((r) => r.fx) }
        ],
        line: { name: "Net new MRR", color: C.ink, values: mv.map((r) => r.end - r.start) }
      });
    });

    const wf = D.waterfall;
    node = card(g, {
      span: "wide",
      title: "A year of recurring revenue, taken apart",
      sub: "Monthly recurring revenue, $'000, " + prettyMonth(wf.period.split(" to ")[0]) + " to " + prettyMonth(wf.period.split(" to ")[1]),
      note: "<b>Source:</b> fact_mrr_bridge_monthly. Churn is split into subscribers who cancelled, renewals whose card failed, and refunds or chargebacks.",
      table: () => ({
        columns: ["Step", "$"],
        rows: [["Opening MRR", fmt(wf.start, "usd0")]].concat(wf.steps.map((s) => [s.label, fmt(s.value, "usd0")]))
          .concat([["Closing MRR", fmt(wf.end, "usd0")]])
      })
    });
    register(node, (n) => EC.waterfall(n, {
      height: 320, yFormat: "usdKs", labelFormat: "usdKs", start: wf.start, end: wf.end,
      startLabel: "Opening MRR", endLabel: "Closing MRR",
      steps: wf.steps.map((s) => ({
        label: { "Voluntary churn": "Cancelled", "Payment-failure churn": "Card failed",
                 "Refunds & chargebacks": "Refunds" }[s.label] || s.label, value: s.value
      }))
    }));
  }

  /* ---------- 2. growth ---------- */
  function growth() {
    const g = section("growth", "The growth engine",
      "Nine acquisition channels, one question: which subscribers pay back the cost of winning them?");

    const ch = D.channels.filter((c) => c.subs_12m > 0);
    let node = card(g, {
      title: "Cheap to acquire, slow to pay back: not the same thing",
      sub: "Cost per new subscriber against 12-month revenue per subscriber, $. Bubble size is subscribers won in the past year",
      note: "<b>Source:</b> fact_marketing_daily, fact_cohort_retention. CAC is the past 12 months' spend per first payment; lifetime value is cumulative net revenue per subscriber for cohorts old enough to be observed for 12 months. Direct/brand has no media cost and is not plotted.",
      table: () => ({
        columns: ["Channel", "New subs (12m)", "Spend (12m)", "CAC", "LTV 6m", "LTV 12m", "LTV:CAC", "Payback (months)"],
        rows: D.channels.map((c) => [c.name, fmt(c.subs_12m, "int"), fmt(c.spend_12m, "usd0"), fmt(c.cac, "usd2"),
        fmt(c.ltv6, "usd2"), fmt(c.ltv12, "usd2"), c.ltv_cac ? fmt(c.ltv_cac, "x1") : "n/a",
        c.payback_months === null ? "n/a" : fmt(c.payback_months, "m1")])
      })
    });
    register(node, (n) => EC.scatter(n, {
      height: 320, xFormat: "usd0", yFormat: "usd0", xTitle: "Customer acquisition cost, $",
      guides: [{ k: 1, label: "LTV = CAC" }, { k: 3, label: "3x" }],
      points: ch.filter((c) => c.cac > 0).map((c) => ({
        x: c.cac, y: c.ltv12, r: c.subs_12m, label: c.name,
        color: c.id === "CH03" ? C.red : c.group === "Organic" ? C.cyan : C.blue,
        rows: [{ k: "CAC", v: fmt(c.cac, "usd2") }, { k: "12-month LTV", v: fmt(c.ltv12, "usd2") },
        { k: "LTV:CAC", v: fmt(c.ltv_cac, "x1") }, { k: "New subs, 12m", v: fmt(c.subs_12m, "int") },
        { k: "Month-1 retention", v: fmt(c.m1_retention, "pct0") }]
      }))
    }));

    node = card(g, {
      title: "Most channels pay for themselves inside a month",
      sub: "Months of gross profit needed to recover acquisition cost, cash basis",
      note: "<b>Source:</b> fact_cohort_retention, fact_marketing_daily. Annual plans are billed up front, so much of the cost is recovered at the first payment; a gross margin of " +
        fmt(D.meta.gross_margin_12m, "pct0") + " is applied to cohort revenue. Paid social is the outlier.",
      table: () => ({
        columns: ["Channel", "Payback (months)", "CAC", "Month-1 retention"],
        rows: D.channels.filter((c) => c.payback_months !== null).map((c) =>
          [c.name, fmt(c.payback_months, "m1"), fmt(c.cac, "usd2"), fmt(c.m1_retention, "pct0")])
      })
    });
    register(node, (n) => EC.barsH(n, {
      xFormat: "m1", labelFormat: "m1", valueLabel: "Months",
      items: ch.filter((c) => c.payback_months !== null).sort((a, b) => a.payback_months - b.payback_months).map((c) => ({
        label: c.name, value: Math.max(c.payback_months, 0.05), color: c.payback_months > 3 ? C.red : C.blue,
        rows: [{ k: "Payback", v: fmt(c.payback_months, "m1") + " months" }, { k: "CAC", v: fmt(c.cac, "usd2") },
        { k: "12-month LTV", v: fmt(c.ltv12, "usd2") }]
      }))
    }));

    const cq = D.cac_quarterly;
    const focus = { CH03: C.red, CH01: C.blue, CH02: C.cyan, CH05: C.yellow };
    node = card(g, {
      span: "wide",
      title: "Paid social got expensive, then got cut",
      sub: "Cost per new subscriber by quarter, $",
      note: "<b>Source:</b> fact_marketing_daily. In the first quarter of 2026 CPM inflation and ad-account restrictions pushed paid-social CAC above $48; budget moved to SEO and creators from April. Grey lines are the remaining channels.",
      table: () => ({
        columns: ["Quarter"].concat(Object.keys(cq.series).map((k) => (D.channels.find((c) => c.id === k) || { name: k }).name)),
        rows: cq.quarters.map((q, i) => [q].concat(Object.keys(cq.series).map((k) => fmt(cq.series[k][i], "usd2"))))
      })
    });
    register(node, (n) => EC.lineChart(n, {
      x: cq.quarters, height: 280, yFormat: "usd0", leftPad: 44,
      xLabels: cq.quarters.map((q) => ({ text: q.slice(2), strong: q.endsWith("Q1") })),
      series: Object.keys(cq.series).filter((k) => !focus[k] && k !== "CH06")
        .map((k) => ({ name: "", color: "#c7d0d5", width: 1.4, values: cq.series[k] }))
        .concat(Object.keys(focus).filter((k) => cq.series[k]).map((k) => ({
          name: (D.channels.find((c) => c.id === k) || {}).name, color: focus[k], values: cq.series[k], format: "usd2"
        })))
    }));

    node = card(g, {
      title: "Blended cost per subscriber is falling",
      sub: "Cost of acquiring one paying subscriber, $",
      note: "<b>Source:</b> fact_marketing_daily, fact_subscribers. Blended CAC divides all acquisition spend by every new subscriber, including those from organic channels; paid CAC counts only paid channels.",
      table: tsTable(["Blended CAC", "Paid CAC"], ["blended_cac_usd", "paid_cac_usd"], "usd2")
    });
    register(node, (n) => EC.lineChart(n, {
      x: months(), height: 240, yFormat: "usd0", tipTitle: prettyMonth,
      series: [{ name: "Paid", color: C.red, values: col("paid_cac_usd"), format: "usd2" },
      { name: "Blended", color: C.blue, values: col("blended_cac_usd"), format: "usd2" }]
    }));

    node = card(g, {
      title: "Free users convert better than they used to",
      sub: "Share of free sign-ups that become paying subscribers, %",
      note: "<b>Source:</b> fact_funnel_daily, fact_subscribers. Improvements follow the earlier paywall (April 2024), the onboarding change (July 2025) and the tighter free message cap (November 2025).",
      table: tsTable(["Conversion", "Free sign-ups"], ["signup_to_paid_cvr", "new_subscribers"], ["pct2", "int"])
    });
    register(node, (n) => EC.lineChart(n, {
      x: months(), height: 240, yFormat: "pct1", zero: false, tipTitle: prettyMonth, labelRight: false,
      series: [{ name: "Conversion", color: C.blue, values: col("signup_to_paid_cvr"), format: "pct2" }]
    }));
  }

  /* ---------- 3. retention & pricing ---------- */
  function retention() {
    const g = section("retention", "Retention and the price of loyalty",
      "A deep annual discount bought cash up front and better retention. The bill arrives when those subscriptions come up for renewal.");

    const co = D.cohort;
    const cols = 19;
    let node = card(g, {
      span: "wide",
      title: "Cohorts hold up better since the July 2025 onboarding change",
      sub: "Share of each monthly cohort still subscribing, %",
      note: "<b>Source:</b> fact_cohort_retention. Rows are the month subscribers first paid; columns are months since. The step down at month 12 is the annual plan coming up for renewal. Win-backs count again, so a row can tick up.",
      table: () => ({
        columns: ["Cohort", "Size"].concat(Array.from({ length: cols }, (_, j) => "M" + j)),
        rows: co.months.map((m, i) => [prettyMonth(m), fmt(co.sizes[i], "int")]
          .concat(co.retention[i].slice(0, cols).map((v) => (v === null ? "" : fmt(v, "pct0")))))
      })
    });
    register(node, (n) => EC.heatmap(n, {
      rowLabels: co.months.map(prettyMonth), colLabels: Array.from({ length: cols }, (_, j) => "M" + j),
      values: co.retention.map((r) => r.slice(0, cols)), format: "pct0", cellHeight: 17, min: 0, max: 0.85,
      rowTitle: "Cohort", colTitle: "Month",
      extra: (i, j) => [{ k: "Cohort size", v: fmt(co.sizes[i], "int") },
      { k: "Revenue per sub", v: fmt(co.ltv[i][j], "usd2") }]
    }));

    const mix = D.plan_mix.slice(idx().from);
    node = card(g, {
      title: "The 70% annual discount rewired the plan mix",
      sub: "Share of new subscribers by plan, %",
      note: "<b>Source:</b> fact_subscribers, dim_price_book. From June 2025 the annual plan was cut to $3.99 a month, against $13.99 monthly. More cash is collected up front, but reported MRR per subscriber falls.",
      table: () => ({
        columns: ["Month", "1 month", "3 months", "12 months"],
        rows: mix.map((r) => [prettyMonth(r.month), fmt(r.P1M, "pct0"), fmt(r.P3M, "pct0"), fmt(r.P12M, "pct0")])
      })
    });
    register(node, (n) => EC.areaStack(n, {
      x: months(), height: 250, tipTitle: prettyMonth,
      series: [{ name: "12 months", color: C.blue, values: mix.map((r) => r.P12M) },
      { name: "3 months", color: C.cyan, values: mix.map((r) => r.P3M) },
      { name: "1 month", color: C.yellow, values: mix.map((r) => r.P1M) }]
    }));

    node = card(g, {
      title: "Cheaper per month, but they stay longer",
      sub: "Revenue per active subscriber per month, $",
      note: "<b>Source:</b> fact_kpi_monthly. MRR per subscriber is the recurring rate; ARPU adds token top-ups and is the better guide to what a subscriber is worth.",
      table: tsTable(["ARPU", "MRR per subscriber"], [(i) => col("arpu_usd")[i], (i) => slice(D.mrr_per_sub)[i]], "usd2")
    });
    register(node, (n) => EC.lineChart(n, {
      x: months(), height: 250, yFormat: "usd0", tipTitle: prettyMonth,
      series: [{ name: "ARPU", color: C.blue, values: col("arpu_usd"), format: "usd2" },
      { name: "MRR/sub", color: C.cyan, values: slice(D.mrr_per_sub), format: "usd2" }]
    }));

    node = card(g, {
      title: "Churn has halved",
      sub: "Subscribers lost each month as a share of the opening base, %",
      note: "<b>Source:</b> fact_mrr_bridge_monthly. Includes cancellations, failed renewal payments, refunds and chargebacks.",
      table: tsTable(["Churn rate", "Month-1 retention"], ["monthly_churn_rate", "m1_retention_prior_cohort"], "pct1")
    });
    register(node, (n) => EC.lineChart(n, {
      x: months(), height: 250, yFormat: "pct0", tipTitle: prettyMonth,
      series: [{ name: "Churn", color: C.red, values: col("monthly_churn_rate"), format: "pct1" },
      { name: "M1 kept", color: C.blue, values: col("m1_retention_prior_cohort"), format: "pct1" }]
    }));
  }

  /* ---------- 4. compute & operations ---------- */
  function operations() {
    const g = section("operations", "Compute, tokens and operations",
      "Every conversation costs GPU time. Serving it more cheaply has done more for margins than any price change.");

    const cp = D.compute;
    const order = ["Video", "Image", "LLM chat", "Speech"].filter((k) => cp.series[k]);
    const cc = { Video: C.red, Image: C.yellow, "LLM chat": C.blue, Speech: C.cyan };
    let node = card(g, {
      title: "Video is the expensive habit",
      sub: "GPU cost by workload, $'000 a month",
      legend: order.map((k) => ({ name: k, color: cc[k] })),
      note: "<b>Source:</b> fact_gpu_daily. Cost falls in steps as models are distilled and traffic moves to reserved capacity: video model v2 (April 2025), caching and video v3 (November 2025), reserved H100s (February 2026).",
      table: () => ({
        columns: ["Month"].concat(order),
        rows: months().map((m, i) => [prettyMonth(m)].concat(order.map((k) => fmt(slice(cp.series[k])[i], "usd0"))))
      })
    });
    register(node, (n) => EC.columnChart(n, {
      x: months(), height: 250, yFormat: "usdKs", tipTitle: prettyMonth,
      series: order.map((k) => ({ name: k, color: cc[k], values: slice(cp.series[k]) }))
    }));

    node = card(g, {
      title: "Cost to serve a subscriber has fallen by three-quarters",
      sub: "GPU cost per active subscriber, $ a month",
      note: "<b>Source:</b> fact_usage_daily, fact_kpi_monthly. Free users are included: they generate most chat volume and none of the revenue, which is why the November 2025 message cap mattered.",
      table: tsTable(["GPU per subscriber", "GPU as % of revenue", "Free-tier GPU cost"],
        ["gpu_cost_per_active_sub_usd", "gpu_cost_pct_revenue", "free_tier_compute_cost_usd"], ["usd2", "pct1", "usd0"])
    });
    register(node, (n) => EC.lineChart(n, {
      x: months(), height: 250, yFormat: "usd0", tipTitle: prettyMonth,
      annotations: [{ at: "2024-11", label: "Video launch" }, { at: "2026-02", label: "Reserved GPUs", align: "left", dy: 24 }],
      series: [{ name: "$/sub", color: C.blue, values: col("gpu_cost_per_active_sub_usd"), format: "usd2" }]
    }));

    node = card(g, {
      title: "Tokens now pay for two-fifths of everything",
      sub: "Token top-ups as a share of net revenue, and the share of subscribers buying them, %",
      note: "<b>Source:</b> fact_revenue_daily, fact_subscribers. Attach rate is the share of active subscribers buying at least one pack in the month; token buyers spend about " +
        fmt(M[M.length - 1].token_arppu_usd, "usd0") + " a month on average.",
      table: tsTable(["Token share of revenue", "Attach rate", "Spend per buyer"],
        ["token_share_of_revenue", "token_attach_rate", "token_arppu_usd"], ["pct1", "pct1", "usd2"])
    });
    register(node, (n) => EC.lineChart(n, {
      x: months(), height: 250, yFormat: "pct0", tipTitle: prettyMonth,
      series: [{ name: "Revenue share", color: C.blue, values: col("token_share_of_revenue"), format: "pct1" },
      { name: "Attach rate", color: C.cyan, values: col("token_attach_rate"), format: "pct1" }]
    }));

    node = card(g, {
      title: "A fifth of buyers bring seven-tenths of token revenue",
      sub: "Share of token revenue by spending segment, %",
      note: "<b>Source:</b> fact_subscribers. Segments split token buyers by lifetime spend: Whale is the top 5%, Heavy the next 15%.",
      table: () => ({
        columns: ["Segment", "Subscribers", "Token revenue", "% of revenue"],
        rows: D.token_segments.map((s) => [s.segment, fmt(s.subs, "int"), fmt(s.revenue, "usd0"), fmt(s.share_revenue, "pct0")])
      })
    });
    register(node, (n) => EC.barsH(n, {
      xFormat: "pct0", labelFormat: "pct0", leftPad: 110, valueLabel: "Share of token revenue",
      items: D.token_segments.filter((s) => s.segment !== "Non-buyer").map((s, i) => ({
        label: s.segment, value: s.share_revenue, color: [C.blue, C.blue, C.cyan, C.cyan][i] || C.cyan,
        rows: [{ k: "Share of token revenue", v: fmt(s.share_revenue, "pct1") },
        { k: "Subscribers", v: fmt(s.subs, "int") }, { k: "Token revenue", v: fmt(s.revenue, "usd0") }]
      }))
    }));

    const pay = D.payments;
    node = card(g, {
      title: "A new acquirer stopped the leak",
      sub: "Share of renewal charges approved, %",
      note: "<b>Source:</b> fact_payments_monthly. Acquirer C, with network tokens and smarter retries, took 70% of card volume from February 2026; failed renewals are the second-biggest source of churn. Crypto renewals are paid by hand and never decline, so they are left off the chart.",
      table: () => ({
        columns: ["Month"].concat(pay.processors),
        rows: months().map((m, i) => [prettyMonth(m)].concat(pay.processors.map((p) => {
          const v = slice(pay.approval[p])[i];
          return v === null ? "" : fmt(v, "pct1");
        })))
      })
    });
    register(node, (n) => EC.lineChart(n, {
      x: months(), height: 250, yFormat: "pct0", zero: false, tipTitle: prettyMonth,
      series: pay.processors.filter((p) => p !== "CRYPTO_GW").map((p, i) => ({
        name: p.replace("ACQ_", "Acquirer "), color: [C.cyan, C.yellow, C.blue][i],
        values: slice(pay.approval[p]), format: "pct1"
      }))
    }));

    node = card(g, {
      title: "Support keeps up, mostly",
      sub: "Share of tickets answered inside the first-response target, %",
      note: "<b>Source:</b> fact_support_tickets. Dips are capacity lagging demand: the launch ramp, the video-generation bugs of late 2024 and the price-change notices of spring 2025.",
      table: tsTable(["SLA met", "Tickets per 1,000 subs", "Average CSAT"], ["sla_met_rate", "tickets_per_1k_subs", "avg_csat"],
        ["pct1", "m1", "m1"])
    });
    register(node, (n) => EC.lineChart(n, {
      x: months(), height: 250, yFormat: "pct0", zero: false, tipTitle: prettyMonth, labelRight: false,
      series: [{ name: "SLA met", color: C.blue, values: col("sla_met_rate"), format: "pct1" }]
    }));
  }

  /* ---------- 5. finance ---------- */
  function finance() {
    const g = section("finance", "Against the plan",
      "Eight months into 2026 the company is ahead of budget on revenue and well under it on compute.");

    const bva = D.bva.filter((b) => Math.abs(b.var) > 20000).slice();
    bva.sort((a, b) => a.var - b.var);
    let node = card(g, {
      span: "wide",
      title: "Where 2026 is beating - and missing - the budget",
      sub: "Variance against budget, January to August 2026, $'000. Positive is favourable",
      note: "<b>Source:</b> fact_pnl_monthly. Costs are negative, so a favourable cost variance means spending less than planned. Lines within $20,000 of budget are omitted.",
      table: () => ({
        columns: ["Line", "Actual", "Budget", "Variance"],
        rows: D.bva.map((b) => [b.line, fmt(b.actual, "usd0"), fmt(b.budget, "usd0"), fmt(b.var, "usd0")])
      })
    });
    register(node, (n) => EC.barsH(n, {
      xFormat: "usdKs", labelFormat: "usdKs", leftPad: 210, rowHeight: 24, valueLabel: "Variance",
      items: bva.map((b) => ({
        label: b.line, value: b.var, color: b.var >= 0 ? C.blue : C.red,
        rows: [{ k: "Actual", v: fmt(b.actual, "usd0") }, { k: "Budget", v: fmt(b.budget, "usd0") },
        { k: "Variance", v: fmt(b.var, "usd0") }]
      }))
    }));

    const q = D.pnl_quarterly;
    node = card(g, {
      title: "Quarterly profit, with the rest of 2026 forecast",
      sub: "EBITDA, $'000. Lighter bars include forecast months",
      legend: [{ name: "Actual", color: C.blue }, { name: "Forecast", color: C.cyan }],
      note: "<b>Source:</b> fact_pnl_monthly. The final quarter is the 8+4 forecast: actuals run to August 2026.",
      table: () => ({
        columns: ["Quarter", "Net revenue", "EBITDA", "Margin"],
        rows: q.map((r) => [r.quarter, fmt(r.revenue, "usd0"), fmt(r.ebitda, "usd0"), fmt(r.margin, "pct1")])
      })
    });
    register(node, (n) => EC.columnChart(n, {
      x: q.map((r) => r.quarter), height: 250, yFormat: "usdKs",
      xLabels: q.map((r) => ({ text: r.quarter.slice(2), strong: r.quarter.endsWith("Q1") })),
      series: [{
        name: "EBITDA", color: C.blue, values: q.map((r) => r.ebitda),
        colors: q.map((r) => (r.quarter >= "2026Q3" ? C.cyan : C.blue))
      }]
    }));

    node = card(g, {
      title: "Cash comes in before revenue is earned",
      sub: "Subscription billings and the deferred revenue balance, $'000",
      note: "<b>Source:</b> fact_revenue_monthly, fact_deferred_revenue. Annual plans are collected up front and recognised over 12 months; the growing deferred balance is revenue already banked in cash.",
      table: tsTable(["Billings", "Recognised revenue", "Deferred balance"],
        ["subscription_billings_usd", "subscription_revenue_usd", "deferred_revenue_eom_usd"], "usd0")
    });
    register(node, (n) => EC.lineChart(n, {
      x: months(), height: 250, yFormat: "usdKs", tipTitle: prettyMonth,
      series: [{ name: "Deferred", color: C.cyan, values: col("deferred_revenue_eom_usd") },
      { name: "Billings", color: C.blue, values: col("subscription_billings_usd") },
      { name: "Recognised", color: C.yellow, values: col("subscription_revenue_usd") }]
    }));
  }

  /* ---------- nav + filters ---------- */
  function controls() {
    document.querySelectorAll(".range button").forEach((b) => {
      b.addEventListener("click", () => {
        state.range = b.dataset.range;
        document.querySelectorAll(".range button").forEach((x) => x.setAttribute("aria-pressed", x === b));
        redraw();
      });
    });
    const links = Array.from(document.querySelectorAll(".nav a"));
    const secs = links.map((a) => document.querySelector(a.getAttribute("href")));
    const onScroll = () => {
      const y = window.scrollY + 90;
      let active = 0;
      secs.forEach((s, i) => { if (s && s.offsetTop <= y) active = i; });
      links.forEach((a, i) => a.classList.toggle("active", i === active));
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  kpis();
  overview();
  growth();
  retention();
  operations();
  finance();
  controls();
  document.getElementById("generated").textContent = D.meta.generated;
})();
