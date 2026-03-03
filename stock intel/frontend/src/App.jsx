import { useState, useEffect, useCallback } from "react";

// ─── CONFIG ──────────────────────────────────────────────────────────────────
const API_BASE = import.meta.env.VITE_API_BASE || "https://your-space.hf.space";

const api = {
  get: async (path) => {
    const r = await fetch(`${API_BASE}${path}`);
    if (!r.ok) throw new Error(`API error ${r.status}`);
    return r.json();
  },
  post: async (path, body) => {
    const r = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`API error ${r.status}`);
    return r.json();
  },
};

// ─── MOCK DATA (fallback when backend is unreachable) ────────────────────────
const MOCK_STOCKS = [
  { ticker: "EQTY.NR", name: "Equity Group", sector: "Banking",
    scores: { daily: 82, monthly: 78, long_term: 85, best_pick: 82 },
    metrics: { pe: 7.2, pb: 0.9, dividend_yield: 0.062, price: 45.50 },
    sparkline: [43.1, 43.8, 44.2, 44.9, 45.1, 44.8, 45.5] },
  { ticker: "SCOM.NR", name: "Safaricom", sector: "Telecom",
    scores: { daily: 71, monthly: 88, long_term: 90, best_pick: 83 },
    metrics: { pe: 12.1, pb: 4.2, dividend_yield: 0.071, price: 18.20 },
    sparkline: [17.5, 17.8, 18.0, 18.3, 18.1, 18.4, 18.2] },
  { ticker: "KCB.NR", name: "KCB Group", sector: "Banking",
    scores: { daily: 76, monthly: 72, long_term: 74, best_pick: 74 },
    metrics: { pe: 4.8, pb: 0.7, dividend_yield: 0.058, price: 28.75 },
    sparkline: [27.8, 28.1, 28.4, 28.0, 28.3, 28.6, 28.75] },
  { ticker: "EABL.NR", name: "EA Breweries", sector: "Consumer",
    scores: { daily: 55, monthly: 61, long_term: 65, best_pick: 60 },
    metrics: { pe: 18.4, pb: 3.1, dividend_yield: 0.035, price: 155.0 },
    sparkline: [152, 153, 154, 153, 155, 154, 155] },
  { ticker: "COOP.NR", name: "Co-op Bank", sector: "Banking",
    scores: { daily: 68, monthly: 65, long_term: 70, best_pick: 68 },
    metrics: { pe: 5.9, pb: 0.8, dividend_yield: 0.052, price: 12.90 },
    sparkline: [12.4, 12.5, 12.7, 12.6, 12.8, 12.9, 12.9] },
];

const MOCK_PORTFOLIO = {
  summary: { total_invested: 250000, current_value: 312000, unrealized_pl: 62000, realized_pl: 8500, return_pct: 0.248 },
  holdings: [
    { ticker: "EQTY.NR", quantity: 500, avg_cost: 38.0, current_price: 45.5, unrealized_pl: 3750, best_pick_score: 82 },
    { ticker: "SCOM.NR", quantity: 1000, avg_cost: 15.2, current_price: 18.2, unrealized_pl: 3000, best_pick_score: 83 },
  ],
};

const MOCK_DETAIL = {
  ticker: "EQTY.NR", name: "Equity Group", sector: "Banking",
  scores: { daily: 82, monthly: 78, long_term: 85, best_pick: 82 },
  price_history: Array.from({ length: 30 }, (_, i) => ({
    date: new Date(Date.now() - (29 - i) * 86400000).toISOString().slice(0, 10),
    close: 42 + Math.random() * 5,
  })),
  fundamentals: { eps: 7.2, bvps: 30.5, revenue: 120e9, debt: 40e9, dividends: 3.0, roe: 0.18, margin: 0.25 },
  my_position: { quantity: 500, avg_cost: 38.0, current_price: 45.5, unrealized_pl: 3750, holding_days: 365 },
};

const MOCK_ANALYTICS = {
  equity_curve: Array.from({ length: 12 }, (_, i) => ({
    date: new Date(2025, i, 1).toISOString().slice(0, 10),
    value: 200000 + i * 9000 + Math.random() * 5000,
  })),
  monthly_performance: Array.from({ length: 12 }, (_, i) => ({
    month: `2025-${String(i + 1).padStart(2, "0")}`,
    return_pct: (Math.random() * 0.1 - 0.02),
  })),
  best_picks: [{ ticker: "EQTY.NR", return_pct: 0.196 }, { ticker: "SCOM.NR", return_pct: 0.197 }],
  worst_picks: [{ ticker: "EABL.NR", return_pct: -0.04 }],
  avg_holding_days: 210,
  projections: [
    { years: 1, projected_value: 376640, assumed_rate: 0.248 },
    { years: 3, projected_value: 584280, assumed_rate: 0.248 },
    { years: 5, projected_value: 906000, assumed_rate: 0.248 },
    { years: 10, projected_value: 2640000, assumed_rate: 0.248 },
  ],
};

// ─── UTILITIES ───────────────────────────────────────────────────────────────
const fmt = {
  kes: (v) => v == null ? "—" : `KES ${Number(v).toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
  pct: (v) => v == null ? "—" : `${(v * 100).toFixed(1)}%`,
  num: (v, d = 2) => v == null ? "—" : Number(v).toFixed(d),
  big: (v) => {
    if (v == null) return "—";
    if (v >= 1e12) return `${(v / 1e12).toFixed(1)}T`;
    if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
    if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
    return Number(v).toLocaleString();
  },
};

const scoreColor = (s) => {
  if (s >= 80) return "#00E5A0";
  if (s >= 60) return "#1F6FEB";
  if (s >= 40) return "#F59E0B";
  return "#EF4444";
};

const scoreLabel = (s) => {
  if (s >= 80) return "Strong";
  if (s >= 60) return "Good";
  if (s >= 40) return "Fair";
  return "Weak";
};

// ─── MINI SPARKLINE SVG ───────────────────────────────────────────────────────
function Spark({ data = [], color = "#1F6FEB", h = 32, w = 80 }) {
  if (!data.length) return <svg width={w} height={h} />;
  const min = Math.min(...data), max = Math.max(...data);
  const range = max - min || 1;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / range) * h;
    return `${x},${y}`;
  }).join(" ");
  const last = data[data.length - 1];
  const first = data[0];
  const up = last >= first;
  const c = up ? "#00E5A0" : "#EF4444";
  return (
    <svg width={w} height={h} style={{ overflow: "visible" }}>
      <polyline points={pts} fill="none" stroke={c} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

// ─── SCORE RING ───────────────────────────────────────────────────────────────
function ScoreRing({ score, size = 56, label }) {
  const r = (size / 2) - 5;
  const circ = 2 * Math.PI * r;
  const dash = (score / 100) * circ;
  const c = scoreColor(score);
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#1E2D45" strokeWidth="4" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={c} strokeWidth="4"
          strokeDasharray={`${dash} ${circ - dash}`} strokeLinecap="round"
          style={{ transition: "stroke-dasharray 0.6s ease" }} />
        <text x={size / 2} y={size / 2} textAnchor="middle" dominantBaseline="central"
          style={{ transform: "rotate(90deg)", transformOrigin: `${size / 2}px ${size / 2}px`, fontSize: 13, fontWeight: 700, fill: c, fontFamily: "inherit" }}>
          {score}
        </text>
      </svg>
      {label && <span style={{ fontSize: 9, color: "#8899AA", letterSpacing: "0.08em", textTransform: "uppercase" }}>{label}</span>}
    </div>
  );
}

// ─── LINE CHART (pure SVG, no deps) ──────────────────────────────────────────
function LineChart({ data = [], valueKey = "value", dateKey = "date", color = "#1F6FEB", height = 160 }) {
  if (!data.length) return <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center", color: "#4A6080" }}>No data</div>;
  const vals = data.map(d => d[valueKey]);
  const min = Math.min(...vals), max = Math.max(...vals);
  const range = max - min || 1;
  const w = 100, h = 100; // viewBox units
  const pts = data.map((d, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((d[valueKey] - min) / range) * (h - 10) - 5;
    return `${x},${y}`;
  }).join(" ");
  const areaBottom = `${w},${h} 0,${h}`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height }} preserveAspectRatio="none">
      <defs>
        <linearGradient id="chartGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={`${pts} ${areaBottom}`} fill="url(#chartGrad)" />
      <polyline points={pts} fill="none" stroke={color} strokeWidth="0.8" strokeLinejoin="round" />
    </svg>
  );
}

// ─── BAR CHART (monthly performance) ─────────────────────────────────────────
function BarChart({ data = [], height = 120 }) {
  if (!data.length) return null;
  const vals = data.map(d => d.return_pct);
  const maxAbs = Math.max(...vals.map(Math.abs), 0.01);
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height, paddingTop: 8 }}>
      {data.map((d, i) => {
        const pct = d.return_pct;
        const barH = Math.abs(pct / maxAbs) * (height * 0.7);
        const up = pct >= 0;
        return (
          <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
            <div style={{ fontSize: 7, color: up ? "#00E5A0" : "#EF4444", fontWeight: 600 }}>{(pct * 100).toFixed(1)}%</div>
            <div style={{ width: "100%", height: barH, background: up ? "#00E5A0" : "#EF4444", borderRadius: "2px 2px 0 0", opacity: 0.85 }} />
            <div style={{ fontSize: 7, color: "#4A6080" }}>{d.month?.slice(5)}</div>
          </div>
        );
      })}
    </div>
  );
}

// ─── STOCK CARD ───────────────────────────────────────────────────────────────
function StockCard({ stock, timing, onClick }) {
  const score = stock.scores[timing] ?? stock.scores.best_pick;
  const c = scoreColor(score);
  const priceUp = stock.sparkline?.length > 1 && stock.sparkline[stock.sparkline.length - 1] >= stock.sparkline[0];

  return (
    <div onClick={() => onClick(stock)} style={{
      background: "linear-gradient(135deg, #0D2140 0%, #0A1A2F 100%)",
      border: "1px solid #1A3050",
      borderRadius: 14,
      padding: "14px 16px",
      display: "flex",
      alignItems: "center",
      gap: 12,
      cursor: "pointer",
      transition: "all 0.18s ease",
      marginBottom: 8,
    }}
      onMouseEnter={e => e.currentTarget.style.borderColor = "#1F6FEB"}
      onMouseLeave={e => e.currentTarget.style.borderColor = "#1A3050"}
    >
      {/* Score */}
      <div style={{ width: 44, height: 44, borderRadius: 10, background: `${c}18`, border: `1.5px solid ${c}40`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
        <span style={{ fontSize: 15, fontWeight: 800, color: c }}>{score}</span>
      </div>

      {/* Info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "#E8F0FF", letterSpacing: "0.02em" }}>{stock.ticker}</div>
        <div style={{ fontSize: 11, color: "#5A7A9A", marginTop: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{stock.name}</div>
        <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
          {stock.metrics.pe && <span style={{ fontSize: 10, color: "#4A6080" }}>P/E <b style={{ color: "#8899AA" }}>{fmt.num(stock.metrics.pe)}</b></span>}
          {stock.metrics.pb && <span style={{ fontSize: 10, color: "#4A6080" }}>P/B <b style={{ color: "#8899AA" }}>{fmt.num(stock.metrics.pb)}</b></span>}
          {stock.metrics.dividend_yield && <span style={{ fontSize: 10, color: "#4A6080" }}>Div <b style={{ color: "#00E5A0" }}>{fmt.pct(stock.metrics.dividend_yield)}</b></span>}
        </div>
      </div>

      {/* Sparkline + Price */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "#E8F0FF" }}>KES {stock.metrics.price}</div>
        <Spark data={stock.sparkline} w={70} h={28} />
      </div>
    </div>
  );
}

// ─── METRIC TILE ──────────────────────────────────────────────────────────────
function MetricTile({ label, value, sub, accent = "#1F6FEB", wide }) {
  return (
    <div style={{
      background: "linear-gradient(135deg, #0D2140, #091828)",
      border: "1px solid #1A3050",
      borderRadius: 12,
      padding: "12px 14px",
      gridColumn: wide ? "1 / -1" : undefined,
    }}>
      <div style={{ fontSize: 10, color: "#4A6080", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 800, color: accent }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: "#3A5070", marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

// ─── TOAST ────────────────────────────────────────────────────────────────────
function Toast({ msg, type = "info", onClose }) {
  useEffect(() => { const t = setTimeout(onClose, 3500); return () => clearTimeout(t); }, []);
  const colors = { info: "#1F6FEB", success: "#00E5A0", error: "#EF4444" };
  return (
    <div style={{
      position: "fixed", bottom: 90, left: "50%", transform: "translateX(-50%)",
      background: "#0D2140", border: `1px solid ${colors[type]}`, borderRadius: 10,
      padding: "10px 20px", color: "#E8F0FF", fontSize: 13, zIndex: 9999,
      boxShadow: `0 0 20px ${colors[type]}40`, maxWidth: "90vw", textAlign: "center",
      animation: "fadeSlide 0.25s ease",
    }}>
      {msg}
    </div>
  );
}

// ─── TRADE MODAL ──────────────────────────────────────────────────────────────
function TradeModal({ ticker, defaultType = "BUY", onClose, onSubmit }) {
  const [form, setForm] = useState({ ticker: ticker || "", trade_type: defaultType, quantity: "", price: "", date: new Date().toISOString().slice(0, 10) });
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  return (
    <div style={{ position: "fixed", inset: 0, background: "#000000CC", zIndex: 1000, display: "flex", alignItems: "flex-end", justifyContent: "center" }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        width: "100%", maxWidth: 480, background: "#0A1828",
        border: "1px solid #1A3050", borderRadius: "20px 20px 0 0",
        padding: "24px 20px 36px", animation: "slideUp 0.22s ease",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <span style={{ fontSize: 16, fontWeight: 700, color: "#E8F0FF" }}>Log Trade</span>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "#4A6080", fontSize: 20, cursor: "pointer" }}>✕</button>
        </div>

        {[
          { label: "Ticker", key: "ticker", type: "text", placeholder: "e.g. EQTY.NR" },
          { label: "Quantity", key: "quantity", type: "number", placeholder: "500" },
          { label: "Price (KES)", key: "price", type: "number", placeholder: "38.00" },
          { label: "Date", key: "date", type: "date" },
        ].map(f => (
          <div key={f.key} style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 11, color: "#4A6080", marginBottom: 5, textTransform: "uppercase", letterSpacing: "0.08em" }}>{f.label}</div>
            <input type={f.type} value={form[f.key]} placeholder={f.placeholder}
              onChange={e => set(f.key, e.target.value)}
              style={{ width: "100%", background: "#0D2140", border: "1px solid #1A3050", borderRadius: 8, padding: "10px 12px", color: "#E8F0FF", fontSize: 14, outline: "none", boxSizing: "border-box" }} />
          </div>
        ))}

        <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
          {["BUY", "SELL"].map(t => (
            <button key={t} onClick={() => set("trade_type", t)} style={{
              flex: 1, padding: "10px", borderRadius: 8, border: "1px solid",
              borderColor: form.trade_type === t ? (t === "BUY" ? "#00E5A0" : "#EF4444") : "#1A3050",
              background: form.trade_type === t ? (t === "BUY" ? "#00E5A018" : "#EF444418") : "transparent",
              color: form.trade_type === t ? (t === "BUY" ? "#00E5A0" : "#EF4444") : "#4A6080",
              fontWeight: 700, fontSize: 13, cursor: "pointer",
            }}>{t}</button>
          ))}
        </div>

        <button onClick={() => onSubmit(form)} style={{
          width: "100%", padding: "13px", borderRadius: 10, border: "none",
          background: "linear-gradient(135deg, #1F6FEB, #1050C0)",
          color: "#FFFFFF", fontWeight: 700, fontSize: 15, cursor: "pointer", letterSpacing: "0.04em",
        }}>Confirm Trade</button>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
//  PAGES
// ═══════════════════════════════════════════════════════════════════════════════

// ─── HOME DASHBOARD ───────────────────────────────────────────────────────────
function HomeDashboard({ stocks, portfolio, onSelectStock }) {
  if (!stocks.length) return <Loader text="Loading market data…" />;
  const best = stocks[0];
  const topUnder = [...stocks].sort((a, b) => b.scores.daily - a.scores.daily).slice(0, 3);
  const topFund = [...stocks].sort((a, b) => b.scores.monthly - a.scores.monthly).slice(0, 3);
  const topLong = [...stocks].sort((a, b) => b.scores.long_term - a.scores.long_term).slice(0, 3);
  const { summary } = portfolio;
  const plPos = summary.unrealized_pl >= 0;

  return (
    <div style={{ paddingBottom: 24 }}>
      {/* Best Pick Hero */}
      <div style={{
        background: "linear-gradient(135deg, #0F2A50 0%, #071422 100%)",
        border: "1px solid #1F6FEB40",
        borderRadius: 16, padding: "20px 18px", marginBottom: 20,
        position: "relative", overflow: "hidden",
      }}>
        <div style={{ position: "absolute", top: -20, right: -20, width: 120, height: 120, background: "#1F6FEB10", borderRadius: "50%", filter: "blur(30px)" }} />
        <div style={{ fontSize: 10, color: "#1F6FEB", letterSpacing: "0.15em", textTransform: "uppercase", marginBottom: 8 }}>⚡ Best Pick Today</div>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <ScoreRing score={best.scores.best_pick} size={64} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 20, fontWeight: 800, color: "#E8F0FF", letterSpacing: "-0.01em" }}>{best.ticker}</div>
            <div style={{ fontSize: 13, color: "#4A6080" }}>{best.name} · {best.sector}</div>
            <div style={{ fontSize: 22, fontWeight: 800, color: "#00E5A0", marginTop: 4 }}>KES {best.metrics.price}</div>
          </div>
          <div>
            <Spark data={best.sparkline} w={80} h={40} />
          </div>
        </div>
        <div style={{ display: "flex", gap: 12, marginTop: 14 }}>
          {[["D", best.scores.daily], ["M", best.scores.monthly], ["L", best.scores.long_term]].map(([l, s]) => (
            <div key={l} style={{ flex: 1, background: "#0A1828", borderRadius: 8, padding: "8px", textAlign: "center" }}>
              <div style={{ fontSize: 10, color: "#4A6080" }}>{l}</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: scoreColor(s) }}>{s}</div>
            </div>
          ))}
        </div>
        <button onClick={() => onSelectStock(best)} style={{
          marginTop: 14, width: "100%", padding: "10px", borderRadius: 10,
          background: "#1F6FEB20", border: "1px solid #1F6FEB50",
          color: "#1F6FEB", fontWeight: 600, fontSize: 13, cursor: "pointer",
        }}>View Details →</button>
      </div>

      {/* Portfolio Mini */}
      {summary.current_value > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 20 }}>
          <MetricTile label="Portfolio Value" value={fmt.kes(summary.current_value)} wide />
          <MetricTile label="Unrealised P/L" value={fmt.kes(summary.unrealized_pl)} accent={plPos ? "#00E5A0" : "#EF4444"} />
          <MetricTile label="Total Return" value={fmt.pct(summary.return_pct)} accent={plPos ? "#00E5A0" : "#EF4444"} />
        </div>
      )}

      {/* Three columns */}
      {[
        { title: "🎯 Undervalued Today", list: topUnder, key: "daily" },
        { title: "📊 Fundamentally Strong", list: topFund, key: "monthly" },
        { title: "🌱 Long-Term Picks", list: topLong, key: "long_term" },
      ].map(({ title, list, key }) => (
        <div key={key} style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: "#8899AA", marginBottom: 10, letterSpacing: "0.05em" }}>{title}</div>
          {list.map(s => <StockCard key={s.ticker} stock={s} timing={key} onClick={onSelectStock} />)}
        </div>
      ))}
    </div>
  );
}

// ─── SCREENER ─────────────────────────────────────────────────────────────────
function Screener({ stocks, onSelectStock }) {
  const [timing, setTiming] = useState("best_pick");
  const [search, setSearch] = useState("");

  const filtered = stocks
    .filter(s => !search || s.ticker.includes(search.toUpperCase()) || s.name.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => b.scores[timing] - a.scores[timing]);

  const pills = [
    { id: "daily", label: "Daily" },
    { id: "monthly", label: "Monthly" },
    { id: "long_term", label: "Long-Term" },
    { id: "best_pick", label: "Best Pick" },
  ];

  return (
    <div>
      <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search ticker or company…"
        style={{ width: "100%", background: "#0D2140", border: "1px solid #1A3050", borderRadius: 10, padding: "11px 14px", color: "#E8F0FF", fontSize: 14, outline: "none", boxSizing: "border-box", marginBottom: 14 }} />

      <div style={{ display: "flex", gap: 8, marginBottom: 18, overflowX: "auto", paddingBottom: 4 }}>
        {pills.map(p => (
          <button key={p.id} onClick={() => setTiming(p.id)} style={{
            padding: "7px 16px", borderRadius: 20, border: "1px solid",
            borderColor: timing === p.id ? "#1F6FEB" : "#1A3050",
            background: timing === p.id ? "#1F6FEB18" : "transparent",
            color: timing === p.id ? "#1F6FEB" : "#4A6080",
            fontWeight: 600, fontSize: 12, cursor: "pointer", whiteSpace: "nowrap",
          }}>{p.label}</button>
        ))}
      </div>

      {filtered.length === 0
        ? <div style={{ textAlign: "center", color: "#4A6080", padding: 40 }}>No stocks found</div>
        : filtered.map(s => <StockCard key={s.ticker} stock={s} timing={timing} onClick={onSelectStock} />)
      }
    </div>
  );
}

// ─── STOCK DETAIL ─────────────────────────────────────────────────────────────
function StockDetail({ ticker, onBack, onTrade }) {
  const [detail, setDetail] = useState(null);
  const [tab, setTab] = useState("overview");
  const [chartRange, setChartRange] = useState("1M");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/api/stock/${ticker}`)
      .then(setDetail)
      .catch(() => setDetail(MOCK_DETAIL))
      .finally(() => setLoading(false));
  }, [ticker]);

  if (loading) return <Loader text="Loading stock data…" />;
  if (!detail) return <div style={{ color: "#EF4444", padding: 20 }}>Failed to load stock data.</div>;

  const { fundamentals: f, my_position: pos, scores } = detail;
  const plPos = pos?.unrealized_pl >= 0;

  const rangeMap = { "1D": 1, "1M": 30, "1Y": 365, "5Y": 1825 };
  const days = rangeMap[chartRange];
  const chartData = (detail.price_history || []).slice(-days).map(d => ({ date: d.date, value: d.close }));

  return (
    <div>
      {/* Header */}
      <button onClick={onBack} style={{ background: "none", border: "none", color: "#4A6080", fontSize: 13, cursor: "pointer", marginBottom: 12, padding: 0, display: "flex", alignItems: "center", gap: 4 }}>
        ← Back
      </button>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 22, fontWeight: 800, color: "#E8F0FF" }}>{detail.ticker}</div>
          <div style={{ fontSize: 13, color: "#4A6080" }}>{detail.name} · {detail.sector}</div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 22, fontWeight: 800, color: "#E8F0FF" }}>
            KES {detail.price_history?.slice(-1)[0]?.close?.toFixed(2) ?? "—"}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 6, marginBottom: 18 }}>
        {["overview", "fundamentals", "my position"].map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            flex: 1, padding: "8px 4px", borderRadius: 8, border: "1px solid",
            borderColor: tab === t ? "#1F6FEB" : "#1A3050",
            background: tab === t ? "#1F6FEB14" : "transparent",
            color: tab === t ? "#1F6FEB" : "#4A6080",
            fontSize: 11, fontWeight: 600, cursor: "pointer", textTransform: "capitalize",
          }}>{t}</button>
        ))}
      </div>

      {tab === "overview" && (
        <>
          {/* Chart range */}
          <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
            {["1D", "1M", "1Y", "5Y"].map(r => (
              <button key={r} onClick={() => setChartRange(r)} style={{
                padding: "5px 12px", borderRadius: 6, border: "1px solid",
                borderColor: chartRange === r ? "#1F6FEB" : "#1A3050",
                background: chartRange === r ? "#1F6FEB18" : "transparent",
                color: chartRange === r ? "#1F6FEB" : "#4A6080",
                fontSize: 11, fontWeight: 600, cursor: "pointer",
              }}>{r}</button>
            ))}
          </div>
          <div style={{ background: "#0A1828", borderRadius: 12, padding: "12px 8px", marginBottom: 18 }}>
            <LineChart data={chartData} valueKey="value" height={180} />
          </div>

          {/* Scores */}
          <div style={{ display: "flex", justifyContent: "space-around", background: "#0A1828", borderRadius: 12, padding: "16px 8px", marginBottom: 12 }}>
            {[["D", scores.daily, "Daily"], ["M", scores.monthly, "Monthly"], ["L", scores.long_term, "Long-Term"], ["BP", scores.best_pick, "Best Pick"]].map(([, s, l]) => (
              <ScoreRing key={l} score={s} size={52} label={l} />
            ))}
          </div>
        </>
      )}

      {tab === "fundamentals" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <MetricTile label="EPS" value={fmt.num(f.eps)} />
          <MetricTile label="Book Value/Share" value={fmt.num(f.bvps)} />
          <MetricTile label="Revenue" value={fmt.big(f.revenue)} />
          <MetricTile label="Total Debt" value={fmt.big(f.debt)} accent="#F59E0B" />
          <MetricTile label="Annual Dividend" value={`KES ${fmt.num(f.dividends)}`} accent="#00E5A0" />
          <MetricTile label="ROE" value={fmt.pct(f.roe)} accent="#00E5A0" />
          <MetricTile label="Profit Margin" value={fmt.pct(f.margin)} />
        </div>
      )}

      {tab === "my position" && (
        <>
          {pos ? (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 16 }}>
              <MetricTile label="Shares Held" value={pos.quantity?.toLocaleString()} />
              <MetricTile label="Avg Cost" value={`KES ${fmt.num(pos.avg_cost)}`} />
              <MetricTile label="Current Price" value={`KES ${fmt.num(pos.current_price)}`} />
              <MetricTile label="Unrealised P/L" value={fmt.kes(pos.unrealized_pl)} accent={plPos ? "#00E5A0" : "#EF4444"} />
              <MetricTile label="Holding Period" value={`${pos.holding_days} days`} wide />
            </div>
          ) : (
            <div style={{ textAlign: "center", color: "#4A6080", padding: 30, background: "#0A1828", borderRadius: 12, marginBottom: 16 }}>
              No position in {ticker} yet.
            </div>
          )}
          <div style={{ display: "flex", gap: 10 }}>
            <button onClick={() => onTrade(ticker, "BUY")} style={{ flex: 1, padding: 13, borderRadius: 10, border: "none", background: "#00E5A020", color: "#00E5A0", fontWeight: 700, fontSize: 14, cursor: "pointer", border: "1px solid #00E5A040" }}>
              Simulate Buy
            </button>
            <button onClick={() => onTrade(ticker, "SELL")} style={{ flex: 1, padding: 13, borderRadius: 10, border: "none", background: "#EF444420", color: "#EF4444", fontWeight: 700, fontSize: 14, cursor: "pointer", border: "1px solid #EF444440" }}>
              Simulate Sell
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// ─── PORTFOLIO ────────────────────────────────────────────────────────────────
function Portfolio({ portfolio, onAddTrade }) {
  const { summary, holdings } = portfolio;
  const plPos = summary.unrealized_pl >= 0;

  return (
    <div>
      {/* Summary */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 20 }}>
        <MetricTile label="Total Invested" value={fmt.kes(summary.total_invested)} wide />
        <MetricTile label="Current Value" value={fmt.kes(summary.current_value)} accent="#1F6FEB" />
        <MetricTile label="Unrealised P/L" value={fmt.kes(summary.unrealized_pl)} accent={plPos ? "#00E5A0" : "#EF4444"} />
        <MetricTile label="Realised P/L" value={fmt.kes(summary.realized_pl)} accent="#F59E0B" />
        <MetricTile label="Total Return" value={fmt.pct(summary.return_pct)} accent={plPos ? "#00E5A0" : "#EF4444"} wide />
      </div>

      {/* Holdings */}
      <div style={{ fontSize: 13, fontWeight: 700, color: "#8899AA", marginBottom: 10, letterSpacing: "0.05em" }}>Holdings</div>
      {holdings.length === 0
        ? <div style={{ textAlign: "center", color: "#4A6080", padding: 30, background: "#0A1828", borderRadius: 12, marginBottom: 16 }}>No holdings yet. Add your first trade!</div>
        : holdings.map(h => {
          const plH = h.unrealized_pl >= 0;
          return (
            <div key={h.ticker} style={{ background: "#0D2140", border: "1px solid #1A3050", borderRadius: 12, padding: "14px 16px", marginBottom: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "#E8F0FF" }}>{h.ticker}</div>
                  <div style={{ fontSize: 11, color: "#4A6080" }}>{h.quantity} shares @ KES {h.avg_cost}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "#E8F0FF" }}>KES {h.current_price}</div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: plH ? "#00E5A0" : "#EF4444" }}>
                    {plH ? "+" : ""}{fmt.kes(h.unrealized_pl)}
                  </div>
                </div>
              </div>
              {h.best_pick_score && (
                <div style={{ fontSize: 10, color: "#4A6080" }}>Best Pick Score: <span style={{ color: scoreColor(h.best_pick_score), fontWeight: 700 }}>{h.best_pick_score}</span></div>
              )}
            </div>
          );
        })}

      <button onClick={onAddTrade} style={{
        width: "100%", padding: 13, borderRadius: 12, border: "1px solid #1F6FEB50",
        background: "#1F6FEB18", color: "#1F6FEB", fontWeight: 700, fontSize: 14, cursor: "pointer", marginTop: 8,
      }}>+ Add Trade</button>
    </div>
  );
}

// ─── ANALYTICS ────────────────────────────────────────────────────────────────
function Analytics({ analytics }) {
  if (!analytics) return <Loader text="Loading analytics…" />;
  const { equity_curve, monthly_performance, best_picks, worst_picks, avg_holding_days, projections } = analytics;

  const downloadCSV = (data, filename) => {
    if (!data?.length) return;
    const keys = Object.keys(data[0]);
    const csv = [keys.join(","), ...data.map(r => keys.map(k => r[k]).join(","))].join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = filename;
    a.click();
  };

  return (
    <div>
      {/* Equity Curve */}
      <div style={{ fontSize: 13, fontWeight: 700, color: "#8899AA", marginBottom: 10 }}>Equity Curve</div>
      <div style={{ background: "#0A1828", borderRadius: 12, padding: "12px 8px", marginBottom: 20 }}>
        <LineChart data={equity_curve} valueKey="value" height={160} color="#1F6FEB" />
      </div>

      {/* Monthly Performance */}
      <div style={{ fontSize: 13, fontWeight: 700, color: "#8899AA", marginBottom: 10 }}>Monthly Returns</div>
      <div style={{ background: "#0A1828", borderRadius: 12, padding: "16px 12px", marginBottom: 20 }}>
        <BarChart data={monthly_performance} height={130} />
      </div>

      {/* Stats row */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 20 }}>
        <MetricTile label="Avg Holding Time" value={`${avg_holding_days ?? "—"} days`} />
        <MetricTile label="Total Trades" value={best_picks?.length + worst_picks?.length || "—"} />
      </div>

      {/* Best / Worst */}
      {[["🏆 Best Picks", best_picks, "#00E5A0"], ["📉 Worst Picks", worst_picks, "#EF4444"]].map(([title, list, color]) => (
        <div key={title} style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: "#8899AA", marginBottom: 10 }}>{title}</div>
          {(list || []).map(p => (
            <div key={p.ticker} style={{ display: "flex", justifyContent: "space-between", background: "#0A1828", borderRadius: 10, padding: "10px 14px", marginBottom: 6 }}>
              <span style={{ color: "#E8F0FF", fontWeight: 600 }}>{p.ticker}</span>
              <span style={{ color, fontWeight: 700 }}>{p.return_pct >= 0 ? "+" : ""}{fmt.pct(p.return_pct)}</span>
            </div>
          ))}
        </div>
      ))}

      {/* Projections */}
      <div style={{ fontSize: 13, fontWeight: 700, color: "#8899AA", marginBottom: 10 }}>Compounding Projections</div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 20 }}>
        {(projections || []).map(p => (
          <MetricTile key={p.years} label={`${p.years} Year${p.years > 1 ? "s" : ""}`} value={fmt.kes(p.projected_value)} sub={`@${fmt.pct(p.assumed_rate)} p.a.`} accent="#1F6FEB" />
        ))}
      </div>

      {/* Exports */}
      <div style={{ display: "flex", gap: 10 }}>
        <button onClick={() => downloadCSV(equity_curve, "equity_curve.csv")} style={{ flex: 1, padding: 11, borderRadius: 10, border: "1px solid #1A3050", background: "transparent", color: "#4A6080", fontSize: 12, cursor: "pointer" }}>
          ↓ Equity CSV
        </button>
        <button onClick={() => downloadCSV(monthly_performance, "monthly_returns.csv")} style={{ flex: 1, padding: 11, borderRadius: 10, border: "1px solid #1A3050", background: "transparent", color: "#4A6080", fontSize: 12, cursor: "pointer" }}>
          ↓ Monthly CSV
        </button>
      </div>
    </div>
  );
}

// ─── LOADER ───────────────────────────────────────────────────────────────────
function Loader({ text = "Loading…" }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: 60, gap: 16 }}>
      <div style={{ width: 36, height: 36, border: "3px solid #1A3050", borderTopColor: "#1F6FEB", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
      <span style={{ color: "#4A6080", fontSize: 13 }}>{text}</span>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
//  APP ROOT
// ═══════════════════════════════════════════════════════════════════════════════
export default function App() {
  const [page, setPage] = useState("home");
  const [stocks, setStocks] = useState([]);
  const [portfolio, setPortfolio] = useState(MOCK_PORTFOLIO);
  const [analytics, setAnalytics] = useState(null);
  const [selectedTicker, setSelectedTicker] = useState(null);
  const [tradeModal, setTradeModal] = useState(null);
  const [toast, setToast] = useState(null);
  const [loading, setLoading] = useState(true);

  const showToast = (msg, type = "info") => setToast({ msg, type });

  // Fetch all stocks
  useEffect(() => {
    api.get("/api/stocks?timing=best_pick")
      .then(d => setStocks(d.stocks || []))
      .catch(() => { setStocks(MOCK_STOCKS); showToast("Backend offline — showing demo data", "info"); })
      .finally(() => setLoading(false));
  }, []);

  // Fetch portfolio
  useEffect(() => {
    api.get("/api/portfolio")
      .then(setPortfolio)
      .catch(() => {});
  }, []);

  // Fetch analytics when on that page
  useEffect(() => {
    if (page === "analytics" && !analytics) {
      api.get("/api/analytics")
        .then(setAnalytics)
        .catch(() => setAnalytics(MOCK_ANALYTICS));
    }
  }, [page]);

  const handleSelectStock = useCallback((stock) => {
    setSelectedTicker(stock.ticker);
    setPage("detail");
  }, []);

  const handleTrade = async (form) => {
    try {
      const result = await api.post("/api/trades", {
        ticker: form.ticker,
        trade_type: form.trade_type,
        quantity: parseInt(form.quantity),
        price: parseFloat(form.price),
        date: form.date,
      });
      setPortfolio(result);
      showToast(`Trade logged: ${form.trade_type} ${form.quantity} ${form.ticker}`, "success");
    } catch {
      showToast("Trade logged locally (backend offline)", "info");
    }
    setTradeModal(null);
  };

  const navItems = [
    { id: "home", icon: "⌂", label: "Home" },
    { id: "screener", icon: "⊞", label: "Screener" },
    { id: "portfolio", icon: "◎", label: "Portfolio" },
    { id: "analytics", icon: "≈", label: "Analytics" },
  ];

  const goTo = (id) => { setPage(id); setSelectedTicker(null); };

  return (
    <div style={{ background: "#060F1C", minHeight: "100vh", color: "#E8F0FF", fontFamily: "'DM Mono', 'Courier New', monospace", maxWidth: 480, margin: "0 auto", position: "relative" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Space+Grotesk:wght@400;600;700;800&display=swap');
        * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
        body { margin: 0; background: #060F1C; }
        input[type=number] { -moz-appearance: textfield; }
        input::-webkit-outer-spin-button, input::-webkit-inner-spin-button { -webkit-appearance: none; }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes fadeSlide { from { opacity: 0; transform: translateX(-50%) translateY(10px); } to { opacity: 1; transform: translateX(-50%) translateY(0); } }
        @keyframes slideUp { from { transform: translateY(100%); } to { transform: translateY(0); } }
        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-thumb { background: #1A3050; border-radius: 4px; }
      `}</style>

      {/* Header */}
      <div style={{ position: "sticky", top: 0, zIndex: 100, background: "#060F1CDD", backdropFilter: "blur(12px)", borderBottom: "1px solid #0E1F33", padding: "12px 18px", display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ width: 32, height: 32, background: "linear-gradient(135deg, #1F6FEB, #0A3A80)", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16 }}>📈</div>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: "#E8F0FF", letterSpacing: "0.02em", fontFamily: "'Space Grotesk', sans-serif" }}>DericBI Stock Intelligence</div>
          <div style={{ fontSize: 9, color: "#1F6FEB", letterSpacing: "0.12em", textTransform: "uppercase" }}>Know more. Decide better.</div>
        </div>
      </div>

      {/* Page Content */}
      <div style={{ padding: "18px 16px 100px" }}>
        {page === "home" && <HomeDashboard stocks={stocks} portfolio={portfolio} onSelectStock={handleSelectStock} />}
        {page === "screener" && <Screener stocks={stocks} onSelectStock={handleSelectStock} />}
        {page === "portfolio" && <Portfolio portfolio={portfolio} onAddTrade={() => setTradeModal({ ticker: "", type: "BUY" })} />}
        {page === "analytics" && <Analytics analytics={analytics} />}
        {page === "detail" && selectedTicker && (
          <StockDetail
            ticker={selectedTicker}
            onBack={() => setPage("screener")}
            onTrade={(ticker, type) => setTradeModal({ ticker, type })}
          />
        )}
      </div>

      {/* Bottom Nav */}
      <div style={{
        position: "fixed", bottom: 0, left: "50%", transform: "translateX(-50%)",
        width: "100%", maxWidth: 480,
        background: "#08121EEE", backdropFilter: "blur(16px)",
        borderTop: "1px solid #0E1F33",
        display: "flex", padding: "8px 0 16px", zIndex: 200,
      }}>
        {navItems.map(n => {
          const active = page === n.id || (page === "detail" && n.id === "screener");
          return (
            <button key={n.id} onClick={() => goTo(n.id)} style={{
              flex: 1, background: "none", border: "none", cursor: "pointer",
              display: "flex", flexDirection: "column", alignItems: "center", gap: 3,
              color: active ? "#1F6FEB" : "#2A4060", transition: "color 0.18s",
            }}>
              <span style={{ fontSize: 20, lineHeight: 1 }}>{n.icon}</span>
              <span style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase" }}>{n.label}</span>
            </button>
          );
        })}
      </div>

      {/* Footer link */}
      <div style={{ position: "fixed", bottom: 68, width: "100%", maxWidth: 480, left: "50%", transform: "translateX(-50%)", textAlign: "center", pointerEvents: "none" }}>
        <a href="https://dericbi.vercel.app" target="_blank" rel="noreferrer" style={{ fontSize: 10, color: "#1A3050", textDecoration: "none", pointerEvents: "all" }}>
          More BI services → dericbi.vercel.app
        </a>
      </div>

      {/* Trade Modal */}
      {tradeModal && (
        <TradeModal
          ticker={tradeModal.ticker}
          defaultType={tradeModal.type}
          onClose={() => setTradeModal(null)}
          onSubmit={handleTrade}
        />
      )}

      {/* Toast */}
      {toast && <Toast msg={toast.msg} type={toast.type} onClose={() => setToast(null)} />}
    </div>
  );
}
