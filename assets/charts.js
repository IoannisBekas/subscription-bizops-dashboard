/* Minimal SVG chart toolkit in the house style of The Economist:
   horizontal gridlines only, black zero line, direct labels, red rule above the title.
   No chart library, no CDN - everything below is plain DOM + SVG. */
(function (global) {
  "use strict";

  const C = {
    red: "#e3120b", blue: "#006ba2", cyan: "#3ebcd2", yellow: "#dba400",
    ink: "#121317", ink2: "#3b4a54", muted: "#6b7c85", grid: "#d7dcdf", surface: "#ffffff",
    // sequential blue ramp (light -> dark), monotonic in lightness
    ramp: ["#e8f1f6", "#cbe2ec", "#a8d0e0", "#7fb8d0", "#559dbc", "#2f7fa5", "#00638d", "#00456e"],
    // MRR movement colours: blues add, reds subtract, grey is neutral
    add: ["#006ba2", "#3ebcd2", "#93d3e0"], cut: ["#e3120b", "#f0736b", "#f7b0ab", "#c2453e"], neutral: "#758d99"
  };
  const NS = "http://www.w3.org/2000/svg";
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  /* ---------- helpers ---------- */
  function el(tag, attrs, parent) {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs || {}) if (attrs[k] !== null && attrs[k] !== undefined) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function text(parent, x, y, s, o) {
    o = o || {};
    const t = el("text", {
      x: x, y: y, "text-anchor": o.anchor || "start", "font-size": o.size || 11.5,
      "font-weight": o.weight || 400, fill: o.fill || C.muted, "font-family": "inherit",
      "dominant-baseline": o.baseline || "auto"
    }, parent);
    t.textContent = s;
    return t;
  }
  const num = (v) => (v === null || v === undefined || Number.isNaN(v) ? null : +v);

  function fmt(v, kind) {
    if (v === null || v === undefined || Number.isNaN(v)) return "n/a";
    const a = Math.abs(v);
    if (v === 0 && String(kind).indexOf("usd") === 0) return "0";
    switch (kind) {
      case "usdM": return (v < 0 ? "-$" : "$") + (a / 1e6).toFixed(a >= 10e6 ? 1 : 2) + "m";
      case "usdK": return (v < 0 ? "-$" : "$") + Math.round(a / 1e3).toLocaleString() + "k";
      case "usdKs": return (v < 0 ? "-$" : "$") + (a / 1e3).toFixed(a >= 100e3 ? 0 : 1) + "k";
      case "usd0": return (v < 0 ? "-$" : "$") + Math.round(a).toLocaleString();
      case "usd2": return (v < 0 ? "-$" : "$") + a.toFixed(2);
      case "pct1": return (v * 100).toFixed(1) + "%";
      case "pct0": return Math.round(v * 100) + "%";
      case "pct2": return (v * 100).toFixed(2) + "%";
      case "k": return a >= 1000 ? (v / 1000).toFixed(a >= 10000 ? 0 : 1) + "k" : Math.round(v).toLocaleString();
      case "int": return Math.round(v).toLocaleString();
      case "x1": return v.toFixed(1) + "x";
      case "m1": return v.toFixed(1);
      default: return String(v);
    }
  }
  function monthLabel(m, withYear) {
    const p = String(m).split("-");
    return withYear ? "'" + p[0].slice(2) : MONTHS[+p[1] - 1];
  }
  function ticks(min, max, count) {
    if (min === max) { min = Math.min(0, min); max = max || 1; }
    const span = max - min, step0 = span / Math.max(1, count);
    const mag = Math.pow(10, Math.floor(Math.log10(step0)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) || 10 * mag;
    const out = [];
    for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(+v.toFixed(10));
    return out;
  }
  function scale(d0, d1, r0, r1) {
    const s = (v) => (d1 === d0 ? r0 : r0 + ((v - d0) / (d1 - d0)) * (r1 - r0));
    s.invert = (p) => (r1 === r0 ? d0 : d0 + ((p - r0) / (r1 - r0)) * (d1 - d0));
    return s;
  }

  /* ---------- tooltip ---------- */
  let tip;
  function tooltip() {
    if (!tip) { tip = document.createElement("div"); tip.id = "tooltip"; document.body.appendChild(tip); }
    return tip;
  }
  function showTip(evt, title, rows) {
    const t = tooltip();
    t.innerHTML = '<div class="tt-title">' + title + "</div>" +
      rows.map((r) => '<div class="tt-row"><span class="k">' +
        (r.color ? '<span class="tt-sw" style="background:' + r.color + '"></span>' : "") + r.k +
        '</span><span class="v">' + r.v + "</span></div>").join("");
    t.style.opacity = 1;
    const pad = 14, w = t.offsetWidth, h = t.offsetHeight;
    let x = evt.clientX + pad, y = evt.clientY - h - pad;
    if (x + w > window.innerWidth - 8) x = evt.clientX - w - pad;
    if (y < 8) y = evt.clientY + pad;
    t.style.left = x + "px";
    t.style.top = y + "px";
  }
  function hideTip() { if (tip) tip.style.opacity = 0; }

  /* ---------- frame: gridlines, y labels, x labels, zero line ---------- */
  function frame(svg, box, yScale, yTickVals, yFmt, xLabels, xPos, opts) {
    opts = opts || {};
    const g = el("g", {}, svg);
    yTickVals.forEach((v) => {
      const y = yScale(v);
      el("line", { x1: box.l, x2: box.r, y1: y, y2: y, stroke: v === 0 ? C.ink : C.grid, "stroke-width": v === 0 ? 1.3 : 1 }, g);
      text(g, box.l - 7, y + 3.5, fmt(v, yFmt), { anchor: "end", fill: C.muted });
    });
    (xLabels || []).forEach((lab, i) => {
      if (lab === null) return;
      text(g, xPos[i], box.b + 15, lab.text !== undefined ? lab.text : lab,
        { anchor: "middle", fill: lab.strong ? C.ink2 : C.muted, weight: lab.strong ? 700 : 400 });
    });
    if (opts.baseline !== false && !yTickVals.includes(0)) {
      el("line", { x1: box.l, x2: box.r, y1: box.b, y2: box.b, stroke: C.ink, "stroke-width": 1.3 }, g);
    }
    return g;
  }

  function monthTicks(months) {
    return months.map((m, i) => {
      const mm = String(m).split("-")[1];
      if (mm === "01") return { text: "'" + String(m).slice(2, 4), strong: true };
      if (mm === "07" && months.length <= 26) return { text: MONTHS[6] };
      return null;
    });
  }

  /* ---------- mounting + resize ---------- */
  function mount(node, draw) {
    const render = () => {
      const w = Math.max(320, node.clientWidth || 600);
      node.innerHTML = "";
      draw(node, w);
    };
    render();
    if (global.ResizeObserver) {
      let t0;
      new ResizeObserver(() => { clearTimeout(t0); t0 = setTimeout(render, 120); }).observe(node);
    } else {
      global.addEventListener("resize", () => { clearTimeout(t0); t0 = setTimeout(render, 150); });
    }
  }

  function svgRoot(node, w, h) {
    const svg = el("svg", { viewBox: "0 0 " + w + " " + h, width: w, height: h, role: "img" }, node);
    svg.addEventListener("mouseleave", hideTip);
    return svg;
  }

  /* ---------- line chart (time series) ---------- */
  function lineChart(node, spec) {
    mount(node, (host, w) => {
      const h = spec.height || 250;
      const m = { t: 12, r: spec.labelRight === false ? 14 : 78, b: 24, l: spec.leftPad || 46 };
      const svg = svgRoot(host, w, h);
      const box = { l: m.l, r: w - m.r, t: m.t, b: h - m.b };
      const vals = spec.series.flatMap((s) => s.values.map(num)).filter((v) => v !== null);
      let lo = spec.min !== undefined ? spec.min : Math.min(...vals);
      let hi = spec.max !== undefined ? spec.max : Math.max(...vals);
      if (spec.zero !== false && lo > 0) lo = 0;
      const pad = (hi - lo) * 0.06;
      const y = scale(lo, hi + pad, box.b, box.t);
      const x = scale(0, spec.x.length - 1, box.l, box.r);
      const tv = ticks(lo, hi + pad, spec.yTicks || 4);
      frame(svg, box, y, tv, spec.yFormat, spec.xLabels || monthTicks(spec.x), spec.x.map((_, i) => x(i)));
      (spec.annotations || []).forEach((a) => {
        const ax = x(spec.x.indexOf(a.at));
        if (Number.isNaN(ax)) return;
        el("line", { x1: ax, x2: ax, y1: box.t, y2: box.b, stroke: C.ink2, "stroke-width": 1, "stroke-dasharray": "3 3", opacity: .6 }, svg);
        const t = text(svg, ax + (a.align === "left" ? -6 : 6), box.t + (a.dy || 10), a.label,
          { anchor: a.align === "left" ? "end" : "start", fill: C.ink2, size: 11, weight: 700 });
        t.setAttribute("paint-order", "stroke");
        t.setAttribute("stroke", C.surface);
        t.setAttribute("stroke-width", 3);
      });
      const labels = [];
      spec.series.forEach((s) => {
        const pts = s.values.map((v, i) => [x(i), num(v) === null ? null : y(v)]);
        let d = "", open = false;
        pts.forEach((p) => {
          if (p[1] === null) { open = false; return; }
          d += (open ? "L" : "M") + p[0].toFixed(1) + "," + p[1].toFixed(1);
          open = true;
        });
        el("path", {
          d: d, fill: "none", stroke: s.color, "stroke-width": s.width || 2.2,
          "stroke-dasharray": s.dash || null, "stroke-linejoin": "round", "stroke-linecap": "round", opacity: s.opacity || 1
        }, svg);
        if (spec.labelRight !== false && s.name) {
          let li = pts.length - 1;
          while (li > 0 && pts[li][1] === null) li--;
          if (pts[li][1] !== null) labels.push({ y: pts[li][1], name: s.name, color: s.color });
        }
      });
      labels.sort((a, b) => a.y - b.y);
      for (let i = 1; i < labels.length; i++) {
        if (labels[i].y - labels[i - 1].y < 13) labels[i].y = labels[i - 1].y + 13;
      }
      labels.forEach((l) => text(svg, box.r + 6, l.y + 4, l.name, { fill: l.color, weight: 700, size: 12 }));
      // hover: crosshair + all series at nearest index
      const hover = el("g", { opacity: 0 }, svg);
      const vline = el("line", { y1: box.t, y2: box.b, stroke: C.ink2, "stroke-width": 1 }, hover);
      const dots = spec.series.map((s) => el("circle", { r: 4, fill: s.color, stroke: C.surface, "stroke-width": 2 }, hover));
      const rect = el("rect", { x: box.l, y: box.t, width: Math.max(1, box.r - box.l), height: Math.max(1, box.b - box.t), fill: "transparent" }, svg);
      rect.addEventListener("mousemove", (e) => {
        const bb = svg.getBoundingClientRect();
        const i = Math.max(0, Math.min(spec.x.length - 1, Math.round(x.invert((e.clientX - bb.left) * (w / bb.width)))));
        hover.setAttribute("opacity", 1);
        vline.setAttribute("x1", x(i));
        vline.setAttribute("x2", x(i));
        spec.series.forEach((s, k) => {
          const v = num(s.values[i]);
          dots[k].setAttribute("opacity", v === null ? 0 : 1);
          if (v !== null) { dots[k].setAttribute("cx", x(i)); dots[k].setAttribute("cy", y(v)); }
        });
        showTip(e, spec.tipTitle ? spec.tipTitle(spec.x[i]) : spec.x[i],
          spec.series.map((s) => ({ k: s.name, v: fmt(num(s.values[i]), s.format || spec.yFormat), color: s.color })));
      });
      rect.addEventListener("mouseleave", () => { hover.setAttribute("opacity", 0); hideTip(); });
    });
  }

  /* ---------- column chart (stacked, supports negatives) ---------- */
  function columnChart(node, spec) {
    mount(node, (host, w) => {
      const h = spec.height || 250;
      const m = { t: 12, r: spec.rightPad || 14, b: 24, l: spec.leftPad || 46 };
      const svg = svgRoot(host, w, h);
      const box = { l: m.l, r: w - m.r, t: m.t, b: h - m.b };
      const n = spec.x.length;
      const step = (box.r - box.l) / n;
      const bw = Math.max(2, step * (spec.barWidth || 0.72));
      let lo = 0, hi = 0;
      spec.x.forEach((_, i) => {
        let p = 0, q = 0;
        spec.series.forEach((s) => { const v = num(s.values[i]) || 0; if (v >= 0) p += v; else q += v; });
        hi = Math.max(hi, p); lo = Math.min(lo, q);
      });
      if (spec.line) spec.line.values.forEach((v) => { if (num(v) !== null) { hi = Math.max(hi, v); lo = Math.min(lo, v); } });
      const y = scale(lo * 1.06, hi * 1.06, box.b, box.t);
      const tv = ticks(lo * 1.06, hi * 1.06, spec.yTicks || 4);
      frame(svg, box, y, tv, spec.yFormat, spec.xLabels || monthTicks(spec.x), spec.x.map((_, i) => box.l + step * (i + .5)));
      spec.x.forEach((xv, i) => {
        const cx = box.l + step * (i + .5) - bw / 2;
        let up = 0, dn = 0;
        const rows = [];
        spec.series.forEach((s) => {
          const v = num(s.values[i]);
          if (v === null || v === 0) { if (v === 0) rows.push({ k: s.name, v: fmt(0, spec.yFormat), color: s.color }); return; }
          const y0 = v >= 0 ? y(up + v) : y(dn);
          const y1 = v >= 0 ? y(up) : y(dn + v);
          el("rect", { x: cx, y: Math.min(y0, y1), width: bw, height: Math.max(1, Math.abs(y1 - y0) - 2), fill: (s.colors && s.colors[i]) || s.color }, svg);
          if (v >= 0) up += v; else dn += v;
          rows.push({ k: s.name, v: fmt(v, spec.yFormat), color: s.color });
        });
        if (spec.line) rows.push({ k: spec.line.name, v: fmt(num(spec.line.values[i]), spec.line.format || spec.yFormat), color: spec.line.color });
        const hit = el("rect", { x: box.l + step * i, y: box.t, width: Math.max(1, step), height: Math.max(1, box.b - box.t), fill: "transparent" }, svg);
        hit.addEventListener("mousemove", (e) => showTip(e, spec.tipTitle ? spec.tipTitle(xv) : xv, rows));
        hit.addEventListener("mouseleave", hideTip);
      });
      if (spec.line) {
        const d = spec.line.values.map((v, i) => (num(v) === null ? null : [box.l + step * (i + .5), y(v)]))
          .filter(Boolean).map((p, k) => (k ? "L" : "M") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join("");
        el("path", { d: d, fill: "none", stroke: spec.line.color, "stroke-width": 2.4, "stroke-linejoin": "round" }, svg);
      }
    });
  }

  /* ---------- waterfall ---------- */
  function waterfall(node, spec) {
    mount(node, (host, w) => {
      const h = spec.height || 300;
      const m = { t: 14, r: 14, b: 58, l: spec.leftPad || 52 };
      const svg = svgRoot(host, w, h);
      const box = { l: m.l, r: w - m.r, t: m.t, b: h - m.b };
      const bars = [{ label: spec.startLabel, value: spec.start, type: "total" }]
        .concat(spec.steps.map((s) => ({ label: s.label, value: s.value, type: "delta" })))
        .concat([{ label: spec.endLabel, value: spec.end, type: "total" }]);
      let run = 0, lo = 0, hi = spec.start;
      const geom = bars.map((b) => {
        if (b.type === "total") { const g = { y0: 0, y1: b.value }; run = b.value; hi = Math.max(hi, b.value); return g; }
        const g = { y0: run, y1: run + b.value };
        run += b.value; hi = Math.max(hi, run); lo = Math.min(lo, run);
        return g;
      });
      const y = scale(Math.min(0, lo), hi * 1.08, box.b, box.t);
      const tv = ticks(Math.min(0, lo), hi * 1.08, 4);
      const step = (box.r - box.l) / bars.length;
      const bw = Math.max(6, step * 0.68);
      frame(svg, box, y, tv, spec.yFormat, bars.map(() => null), []);
      bars.forEach((b, i) => {
        const cx = box.l + step * (i + .5);
        const y0 = y(geom[i].y0), y1 = y(geom[i].y1);
        const col = b.type === "total" ? C.ink : (b.value >= 0 ? C.blue : C.red);
        el("rect", { x: cx - bw / 2, y: Math.min(y0, y1), width: bw, height: Math.max(2, Math.abs(y1 - y0)), fill: col }, svg);
        if (i < bars.length - 1) {
          el("line", { x1: cx - bw / 2, x2: cx + step + bw / 2, y1: y1, y2: y1, stroke: C.muted, "stroke-width": 1, "stroke-dasharray": "2 2" }, svg);
        }
        const above = b.value >= 0;
        text(svg, cx, (above ? Math.min(y0, y1) - 6 : Math.max(y0, y1) + 13), fmt(b.value, spec.labelFormat || spec.yFormat),
          { anchor: "middle", fill: b.type === "total" ? C.ink : col, weight: 700, size: 11.5 });
        const words = String(b.label).split(" ");
        const lines = words.length > 2 ? [words.slice(0, Math.ceil(words.length / 2)).join(" "), words.slice(Math.ceil(words.length / 2)).join(" ")] : [b.label];
        lines.forEach((ln, k) => text(svg, cx, box.b + 15 + k * 12, ln, { anchor: "middle", fill: C.ink2, size: 11 }));
        const hit = el("rect", { x: cx - step / 2, y: box.t, width: Math.max(1, step), height: Math.max(1, box.b - box.t), fill: "transparent" }, svg);
        hit.addEventListener("mousemove", (e) => showTip(e, b.label, [{ k: b.type === "total" ? "MRR" : "Change", v: fmt(b.value, spec.yFormat), color: col }]));
        hit.addEventListener("mouseleave", hideTip);
      });
    });
  }

  /* ---------- scatter ---------- */
  function scatter(node, spec) {
    mount(node, (host, w) => {
      const h = spec.height || 300;
      const m = { t: 16, r: 18, b: 42, l: spec.leftPad || 50 };
      const svg = svgRoot(host, w, h);
      const box = { l: m.l, r: w - m.r, t: m.t, b: h - m.b };
      const xs = spec.points.map((p) => p.x), ys = spec.points.map((p) => p.y);
      const x = scale(0, Math.max(...xs) * 1.18, box.l, box.r);
      const y = scale(0, Math.max(...ys) * 1.15, box.b, box.t);
      const xt = ticks(0, Math.max(...xs) * 1.18, 4), yt = ticks(0, Math.max(...ys) * 1.15, 4);
      frame(svg, box, y, yt, spec.yFormat, xt.map((v) => ({ text: fmt(v, spec.xFormat) })), xt.map((v) => x(v)));
      (spec.guides || []).forEach((g) => {
        const pts = [[0, 0], [Math.max(...xs) * 1.18, Math.max(...xs) * 1.18 * g.k]].map((p) => [x(p[0]), y(p[1])]);
        el("line", { x1: pts[0][0], y1: pts[0][1], x2: pts[1][0], y2: pts[1][1], stroke: C.muted, "stroke-width": 1, "stroke-dasharray": "4 3" }, svg);
        const lx = Math.min(box.r - 4, pts[1][0]), ly = Math.max(box.t + 10, pts[1][1]);
        text(svg, lx - 2, ly - 4, g.label, { anchor: "end", fill: C.muted, size: 10.5 });
      });
      const rmax = Math.max(...spec.points.map((p) => p.r || 1));
      const placed = [];
      spec.points.forEach((p) => {
        const rr = 5 + 16 * Math.sqrt((p.r || 1) / rmax);
        const cx = x(p.x), cy = y(p.y);
        el("circle", { cx: cx, cy: cy, r: rr, fill: p.color || C.blue, "fill-opacity": .78, stroke: C.surface, "stroke-width": 2 }, svg);
        let ly = cy - rr - 5;
        while (placed.some((q) => Math.abs(q.x - cx) < 4.2 * Math.max(p.label.length, q.len) && Math.abs(q.y - ly) < 12)) ly += 13;
        if (ly > cy - rr - 5 + 26) ly = cy + rr + 13;
        placed.push({ x: cx, y: ly, len: p.label.length });
        const t = text(svg, cx, ly, p.label, { anchor: "middle", fill: C.ink2, size: 11, weight: 700 });
        t.setAttribute("paint-order", "stroke");
        t.setAttribute("stroke", C.surface);
        t.setAttribute("stroke-width", 3.5);
        const hit = el("circle", { cx: cx, cy: cy, r: rr + 4, fill: "transparent" }, svg);
        hit.addEventListener("mousemove", (e) => showTip(e, p.label, p.rows));
        hit.addEventListener("mouseleave", hideTip);
      });
      text(svg, (box.l + box.r) / 2, h - 6, spec.xTitle, { anchor: "middle", fill: C.ink2, size: 11.5, weight: 700 });
    });
  }

  /* ---------- horizontal bars ---------- */
  function barsH(node, spec) {
    mount(node, (host, w) => {
      const rowH = spec.rowHeight || 26;
      const h = spec.items.length * rowH + 34;
      const m = { t: 6, r: spec.rightPad || 56, b: 26, l: Math.min(spec.leftPad || 150, w * 0.42) };
      const svg = svgRoot(host, w, h);
      const box = { l: m.l, r: w - m.r, t: m.t, b: h - m.b };
      const vals = spec.items.map((d) => d.value);
      const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
      const x = scale(lo, hi * 1.02 || 1, box.l, box.r);
      const tv = ticks(lo, hi * 1.02 || 1, 4);
      tv.forEach((v) => {
        el("line", { x1: x(v), x2: x(v), y1: box.t, y2: box.b, stroke: v === 0 ? C.ink : C.grid, "stroke-width": v === 0 ? 1.3 : 1 }, svg);
        text(svg, x(v), box.b + 15, fmt(v, spec.xFormat), { anchor: "middle", fill: C.muted });
      });
      spec.items.forEach((d, i) => {
        const yy = box.t + i * rowH;
        const x0 = x(Math.min(0, d.value)), x1 = x(Math.max(0, d.value));
        el("rect", { x: x0, y: yy + 3, width: Math.max(1, x1 - x0), height: rowH - 10, fill: d.color || C.blue, rx: 0 }, svg);
        text(svg, m.l - 8, yy + rowH / 2 + 1, d.label, { anchor: "end", fill: C.ink2, size: 12, baseline: "middle" });
        const lab = fmt(d.value, spec.labelFormat || spec.xFormat);
        const inside = d.value < 0 && x0 - lab.length * 6.4 < m.l;
        text(svg, d.value >= 0 ? x1 + 6 : (inside ? x0 + 6 : x0 - 6), yy + rowH / 2 + 1, lab,
          { anchor: d.value >= 0 || inside ? "start" : "end", fill: inside ? "#fff" : C.ink2, size: 11.5, weight: 700, baseline: "middle" });
        if (spec.reference !== undefined) {
          el("line", { x1: x(spec.reference), x2: x(spec.reference), y1: box.t, y2: box.b, stroke: C.ink, "stroke-width": 1.2, "stroke-dasharray": "4 3" }, svg);
        }
        const hit = el("rect", { x: box.l, y: yy, width: Math.max(1, box.r - box.l), height: rowH, fill: "transparent" }, svg);
        hit.addEventListener("mousemove", (e) => showTip(e, d.label, d.rows || [{ k: spec.valueLabel || "Value", v: fmt(d.value, spec.xFormat), color: d.color || C.blue }]));
        hit.addEventListener("mouseleave", hideTip);
      });
    });
  }

  /* ---------- heatmap ---------- */
  function heatmap(node, spec) {
    mount(node, (host, w) => {
      const m = { t: 22, r: 8, b: 8, l: spec.leftPad || 56 };
      const cols = spec.colLabels.length, rows = spec.rowLabels.length;
      const cw = Math.max(10, (w - m.l - m.r) / cols);
      const ch = spec.cellHeight || 16;
      const h = m.t + rows * ch + m.b;
      const svg = svgRoot(host, w, h);
      const vals = spec.values.flat().filter((v) => v !== null && v !== undefined);
      const lo = spec.min !== undefined ? spec.min : Math.min(...vals);
      const hi = spec.max !== undefined ? spec.max : Math.max(...vals);
      const color = (v) => {
        const t = Math.max(0, Math.min(1, (v - lo) / (hi - lo || 1)));
        return C.ramp[Math.min(C.ramp.length - 1, Math.floor(t * C.ramp.length))];
      };
      spec.colLabels.forEach((c, j) => {
        if (cols > 14 && j % 2) return;
        text(svg, m.l + cw * (j + .5), m.t - 7, c, { anchor: "middle", fill: C.muted, size: 10.5 });
      });
      spec.rowLabels.forEach((rlab, i) => {
        text(svg, m.l - 7, m.t + ch * i + ch / 2 + 3.5, rlab, { anchor: "end", fill: C.ink2, size: 10.5 });
        spec.values[i].forEach((v, j) => {
          if (v === null || v === undefined) return;
          const fill = color(v);
          const cell = el("rect", { x: m.l + cw * j, y: m.t + ch * i, width: cw - 1.5, height: ch - 1.5, fill: fill }, svg);
          if (cw > 26 && spec.showValues !== false) {
            const t = (v - lo) / (hi - lo || 1);
            text(svg, m.l + cw * (j + .5), m.t + ch * i + ch / 2 + 3, fmt(v, spec.format),
              { anchor: "middle", fill: t > 0.62 ? "#fff" : C.ink2, size: 9.5 });
          }
          cell.addEventListener("mousemove", (e) => showTip(e, spec.rowTitle + " " + rlab,
            [{ k: spec.colTitle + " " + spec.colLabels[j], v: fmt(v, spec.format), color: fill }].concat(spec.extra ? spec.extra(i, j) : [])));
          cell.addEventListener("mouseleave", hideTip);
        });
      });
    });
  }

  /* ---------- 100% stacked area ---------- */
  function areaStack(node, spec) {
    mount(node, (host, w) => {
      const h = spec.height || 240;
      const m = { t: 12, r: spec.rightPad || 96, b: 24, l: spec.leftPad || 46 };
      const svg = svgRoot(host, w, h);
      const box = { l: m.l, r: w - m.r, t: m.t, b: h - m.b };
      const n = spec.x.length;
      const x = scale(0, n - 1, box.l, box.r);
      const y = scale(0, 1, box.b, box.t);
      const tv = [0, .25, .5, .75, 1];
      frame(svg, box, y, tv, "pct0", spec.xLabels || monthTicks(spec.x), spec.x.map((_, i) => x(i)));
      const cum = new Array(n).fill(0);
      spec.series.forEach((s) => {
        const top = s.values.map((v, i) => cum[i] + (num(v) || 0));
        const d = top.map((v, i) => (i ? "L" : "M") + x(i).toFixed(1) + "," + y(v).toFixed(1)).join("") +
          cum.slice().reverse().map((v, k) => "L" + x(n - 1 - k).toFixed(1) + "," + y(v).toFixed(1)).join("") + "Z";
        el("path", { d: d, fill: s.color, "fill-opacity": .92, stroke: C.surface, "stroke-width": 1 }, svg);
        const mid = (cum[n - 1] + top[n - 1]) / 2;
        text(svg, box.r + 6, y(mid) + 4, s.name, { fill: s.color, weight: 700, size: 12 });
        for (let i = 0; i < n; i++) cum[i] = top[i];
      });
      const hover = el("line", { y1: box.t, y2: box.b, stroke: C.ink, "stroke-width": 1, opacity: 0 }, svg);
      const rect = el("rect", { x: box.l, y: box.t, width: Math.max(1, box.r - box.l), height: Math.max(1, box.b - box.t), fill: "transparent" }, svg);
      rect.addEventListener("mousemove", (e) => {
        const bb = svg.getBoundingClientRect();
        const i = Math.max(0, Math.min(n - 1, Math.round(x.invert((e.clientX - bb.left) * (w / bb.width)))));
        hover.setAttribute("opacity", 1);
        hover.setAttribute("x1", x(i));
        hover.setAttribute("x2", x(i));
        showTip(e, spec.tipTitle ? spec.tipTitle(spec.x[i]) : spec.x[i],
          spec.series.map((s) => ({ k: s.name, v: fmt(num(s.values[i]), "pct0"), color: s.color })));
      });
      rect.addEventListener("mouseleave", () => { hover.setAttribute("opacity", 0); hideTip(); });
    });
  }

  /* ---------- sparkline ---------- */
  function sparkline(node, values, color) {
    mount(node, (host, w) => {
      const h = 26, vals = values.map(num).filter((v) => v !== null);
      const lo = Math.min(...vals), hi = Math.max(...vals);
      const svg = svgRoot(host, w, h);
      const x = scale(0, values.length - 1, 1, w - 1);
      const y = scale(lo, hi, h - 3, 3);
      let d = "", open = false;
      values.forEach((v, i) => {
        if (num(v) === null) { open = false; return; }
        d += (open ? "L" : "M") + x(i).toFixed(1) + "," + y(v).toFixed(1);
        open = true;
      });
      el("path", { d: d, fill: "none", stroke: color || C.blue, "stroke-width": 1.6 }, svg);
      const last = values.length - 1;
      if (num(values[last]) !== null) el("circle", { cx: x(last), cy: y(values[last]), r: 2.6, fill: color || C.blue }, svg);
    });
  }

  global.EC = { C, fmt, lineChart, columnChart, waterfall, scatter, barsH, heatmap, areaStack, sparkline, monthLabel };
})(window);
