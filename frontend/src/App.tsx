import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { loadDashboard } from "./services/dashboard";
import { calculate } from "./services/scenario";
import type { DashboardProduct, Scenario, Supplier } from "./types/dashboard";
import "./App.css";

type Page = "Overview" | "Recommendations" | "Sales history" | "Data quality";
type IconName = "grid" | "list" | "chart" | "shield" | "search" | "download" | "box" | "truck" | "arrow" | "close";
const nav: { label: Page; icon: IconName }[] = [
  { label: "Overview", icon: "grid" }, { label: "Recommendations", icon: "list" },
  { label: "Sales history", icon: "chart" }, { label: "Data quality", icon: "shield" },
];
const defaultScenario: Scenario = { seasonality: true, growth: true, stockout: false };
const number = (n: number) => n.toLocaleString("en-US", { maximumFractionDigits: 1 });
const date = (s: string) => new Date(`${s}T12:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, ReactNode> = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
    list: <><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6M9 16h4"/></>,
    chart: <path d="M4 3v17h17M8 15v-4m5 4V6m5 9V9"/>,
    shield: <path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6zM8 12l3 3 5-6"/>,
    search: <><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></>,
    download: <path d="M12 3v12m-4-4 4 4 4-4M4 15v5h16v-5"/>,
    box: <path d="m12 2 9 5v10l-9 5-9-5V7zM3 7l9 5 9-5M12 12v10M7 4.8l9 5"/>,
    truck: <><path d="M2 5h12v12H2zM14 9h4l4 5v3h-8"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="18" r="2"/></>,
    arrow: <path d="M5 12h14m-5-5 5 5-5 5"/>, close: <path d="m6 6 12 12M18 6 6 18"/>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function ProductArt({ kind }: { kind: DashboardProduct["kind"] }) {
  return <span className={`product-art art-${kind}`} aria-hidden="true"><svg viewBox="0 0 48 48" fill="none">
    {kind === "cable" ? <><ellipse cx="24" cy="25" rx="18" ry="12" fill="#334653"/>{[7,10,13,16].map(r => <ellipse key={r} cx="24" cy="25" rx={r} ry={r * .6} stroke="#a9b7ba" strokeWidth="1.2"/>)}<path d="M39 28v10h-7" stroke="#334653" strokeWidth="3"/></> : kind === "breaker" ? <><rect x="14" y="5" width="20" height="38" rx="3" fill="#e5e9e7" stroke="#98a8aa"/><path d="M16 12h16M16 35h16" stroke="#a5b2b3"/><rect x="19" y="17" width="10" height="11" rx="1" fill="#204a50"/><path d="M19 18h10" stroke="#17a68a" strokeWidth="3"/><circle cx="24" cy="9" r="1.5" fill="#697a7e"/></> : kind === "light" ? <><rect x="5" y="14" width="38" height="22" rx="4" fill="#e8eceb" stroke="#9daead"/><rect x="9" y="18" width="30" height="12" rx="2" fill="#fffbdf"/><circle cx="37" cy="33" r="1" fill="#109887"/></> : kind === "box" ? <><path d="m8 14 16-7 16 7v22l-16 7-16-7z" fill="#c9d3d3" stroke="#8c9fa0"/><path d="m8 14 16 7 16-7M24 21v22" stroke="#91a4a6"/><ellipse cx="17" cy="27" rx="5" ry="7" fill="#92a5a7"/><ellipse cx="32" cy="28" rx="4" ry="6" fill="#a3b4b5"/></> : <><rect x="7" y="6" width="34" height="36" rx="5" fill="#e9edeb" stroke="#9eb0b0"/><rect x="12" y="11" width="24" height="26" rx="3" fill="#fafcf9" stroke="#c4ceca"/>{kind === "socket" ? <><circle cx="24" cy="24" r="8" stroke="#b5c2bd"/><circle cx="21" cy="24" r="1.5" fill="#607572"/><circle cx="27" cy="24" r="1.5" fill="#607572"/></> : <path d="M14 34h20" stroke="#b1c0bb"/>}</>}
  </svg></span>;
}

function HistoryChart({ product }: { product: DashboardProduct }) {
  const history = product.history;
  const values = history.flatMap(p => p.quantity === null ? [] : [p.quantity]);
  const min = Math.min(0, ...values), max = Math.max(1, ...values), span = max - min || 1;
  const y = (v: number) => 178 - ((v - min) / span) * 143;
  const x = (i: number) => 65 + i * 55;
  const segments: string[] = []; let segment = "";
  history.forEach((v, i) => {
    if (v.quantity === null) { if (segment) segments.push(segment); segment = ""; }
    else segment += `${segment ? " L" : "M"}${x(i)},${y(v.quantity)}`;
  });
  if (segment) segments.push(segment);
  return <section className="card history-card" aria-labelledby="history-title">
    <div className="card-heading"><div><h2 id="history-title">Sales history</h2><p>{product.name} <span className="subtle-dot">·</span> Sep 2025–Aug 2026</p></div><span className="chart-legend"><i/>Imported actuals</span></div>
    <div className="chart-scroll"><svg className="history-chart" viewBox="0 0 710 220" role="img" aria-label={`Monthly sales of ${product.name}, in ${product.unit}. Exact values are in the expandable table below.`}>
      {[0,1,2,3].map(i => { const v = min + span * i / 3; return <g key={i}><line x1="65" x2="670" y1={y(v)} y2={y(v)} stroke="#e8eef0"/><text x="53" y={y(v)+4} textAnchor="end">{number(v)}</text></g>; })}
      {segments.map((d,i) => <path key={i} d={d} fill="none" stroke="#008b7c" strokeWidth="2.8" strokeLinejoin="round"/>)}
      {history.map((v,i) => <g key={v.month}>{v.quantity !== null && <circle cx={x(i)} cy={y(v.quantity)} r="4" fill="#008b7c"><title>{v.month}: {number(v.quantity)} {product.unit}</title></circle>}<text x={x(i)} y="207" textAnchor="middle">{date(`${v.month}-01`).split(" ")[1]}</text></g>)}
    </svg></div>
    <div className="chart-footer"><span>Units: {product.unit} · Blank source cells remain missing.</span><span className="source-tag">Excel source</span></div>
    <details className="source-details"><summary>View values & source</summary><p>{product.sourceFile} · {product.sourceSheet}, row {product.sourceRow}. September 2026 is excluded because the month is incomplete.</p><div className="values-grid">{history.map(h => <div key={h.month}><span>{h.month}</span><strong>{h.quantity === null ? "Missing" : number(h.quantity)}</strong></div>)}</div></details>
  </section>;
}

function Details({ product: p, scenario, setScenario, onClose }: { product: DashboardProduct; scenario: Scenario; setScenario: (s: Scenario) => void; onClose: () => void }) {
  const c = calculate(p, scenario);
  const toggles: { key: keyof Scenario; label: string; text: string }[] = [
    { key: "seasonality", label: "Seasonality", text: `Example adjustment: +${number(p.seasonalUnits)} ${p.unit}` },
    { key: "growth", label: "Growth trend", text: `Example adjustment: +${number(p.growthUnits)} ${p.unit}` },
    { key: "stockout", label: "Stockout correction", text: `Example adjustment: +${number(p.correctionUnits)} ${p.unit}` },
  ];
  return <aside className="card detail-card" aria-labelledby="detail-title">
    <div className="detail-top"><span className="eyebrow">THE DECISION, EXPLAINED</span><button className="icon-button" onClick={onClose} aria-label="Close product details"><Icon name="close" size={17}/></button></div>
    <h2 id="detail-title">Why order {number(c.order)}?</h2><p className="detail-product">{p.name}</p><p className="sku-line">{p.sku} <span>· {p.supplier}</span></p>
    <div className="example-note">Illustrative scenario <span>All planning inputs below are examples.</span></div>
    <dl className="breakdown">
      <div><dt>Forecast <small>(next period)</small></dt><dd>{number(c.forecast)}</dd></div>
      <div><dt>Safety stock</dt><dd>+{number(p.safetyStock)}</dd></div>
      <div><dt>Available stock <small>{number(p.stock)} on hand − {number(p.reserved)} reserved</small></dt><dd>−{number(c.available)}</dd></div>
      <div><dt>Arriving in time <small>Assumed within planning period</small></dt><dd>−{number(p.incoming)}</dd></div>
      <div className="subtotal"><dt>Net requirement <small>Minimum zero</small></dt><dd>{number(c.net)}</dd></div>
      <div><dt>Order multiple</dt><dd>{number(p.orderMultiple)}</dd></div>
    </dl>
    <div className="order-total" aria-live="polite"><span>Recommended order</span><strong>{number(c.order)} <small>{p.unit}</small></strong></div>
    <p className="rounding-note">{c.order > c.net ? `Rounded up from ${number(c.net)} to a multiple of ${number(p.orderMultiple)}.` : "No additional rounding needed."} {p.orderRuleNote}</p>
    <div className="delivery-note"><Icon name="truck" size={24}/><div><strong>{number(p.incoming)} {p.unit} expected</strong><span>{date(p.arrivalDate)} 2026 · Example delivery</span></div></div>
    <div className="scenario-heading"><h3>What changes the order?</h3><button className="text-button" onClick={() => setScenario({ ...defaultScenario })}>Reset</button></div>
    <div className="toggles">{toggles.map(t => <label className="toggle-row" key={t.key}><span><strong>{t.label}</strong><small>{t.text}</small></span><input type="checkbox" checked={scenario[t.key]} onChange={e => setScenario({ ...scenario, [t.key]: e.target.checked })}/><span className="switch" aria-hidden="true"/></label>)}</div>
    <p className="detail-foot"><Icon name="shield" size={16}/>Scenario controls use sample arithmetic, not the forecasting engine.</p>
  </aside>;
}

function exportCsv(products: DashboardProduct[], scenarios: Record<string, Scenario>) {
  const cell = (v: string | number) => { let s = String(v); if (/^[=+\-@\t\r]/.test(s)) s = `'${s}`; return `"${s.replaceAll('"', '""')}"`; };
  const rows: (string | number)[][] = [["Data mode", "SKU", "Product", "Supplier", "Unit", "Available (example)", "Incoming (example)", "Forecast (example)", "Order (example)", "Seasonality enabled", "Growth enabled", "Stockout correction enabled"]];
  for (const p of products) { const s = scenarios[p.sku] ?? defaultScenario; const c = calculate(p, s); rows.push(["ILLUSTRATIVE DEMO - NOT A PURCHASE ORDER", p.sku, p.name, p.supplier, p.unit, c.available, p.incoming, c.forecast, c.order, String(s.seasonality), String(s.growth), String(s.stockout)]); }
  const url = URL.createObjectURL(new Blob(["\uFEFF" + rows.map(r => r.map(cell).join(",")).join("\r\n")], { type: "text/csv;charset=utf-8;" }));
  const a = document.createElement("a"); a.href = url; a.download = "pairadox-demo-recommendations.csv"; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function App() {
  const [page, setPage] = useState<Page>("Recommendations");
  const [products, setProducts] = useState<DashboardProduct[]>([]);
  const [loading, setLoading] = useState(true), [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [supplier, setSupplier] = useState<Supplier | "All suppliers">("All suppliers");
  const [search, setSearch] = useState("");
  const [selectedSku, setSelectedSku] = useState<string | null>("300200745_");
  const [scenarios, setScenarios] = useState<Record<string, Scenario>>({});
  const [notice, setNotice] = useState("");
  useEffect(() => {
    let active = true; setLoading(true); setError("");
    loadDashboard().then(data => { if (active) setProducts(data); }).catch(() => { if (active) setError("The dashboard data could not be loaded. Please try again."); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [attempt]);
  const query = search.trim().toLowerCase();
  const filtered = products.filter(p => (supplier === "All suppliers" || p.supplier === supplier) && [p.sku, p.name, p.sourceName, p.supplier].some(v => v.toLowerCase().includes(query)));
  const selected = filtered.find(p => p.sku === selectedSku);
  const historyProduct = selected ?? filtered[0];
  const attention = filtered.filter(p => p.priority !== "low" && calculate(p, scenarios[p.sku] ?? defaultScenario).order > 0).length;
  const headings: Record<Page, [string, string]> = {
    Overview: ["Your purchasing workspace", "A clear view of what needs attention, and why."],
    Recommendations: ["Purchase recommendations", "Understand every order before you place it."],
    "Sales history": ["The story behind demand", "Explore actual monthly sales from the supplied workbooks."],
    "Data quality": ["Know what the data can tell you", "Source limitations stay visible before they become decisions."],
  };
  function changeSupplier(value: Supplier | "All suppliers") { setSupplier(value); const first = products.find(p => (value === "All suppliers" || p.supplier === value) && [p.sku,p.name,p.sourceName,p.supplier].some(v => v.toLowerCase().includes(query))); setSelectedSku(first?.sku ?? null); }
  return <div className="app-shell">
    <a className="skip-link" href="#main">Skip to content</a>
    <aside className="sidebar"><a className="wordmark" href="#main" onClick={() => setPage("Recommendations")}>PAIRADO<span>X</span><i/></a><p className="nav-caption">PURCHASING WORKSPACE</p><nav aria-label="Main navigation">{nav.map(n => <button key={n.label} className={page === n.label ? "nav-item active" : "nav-item"} aria-current={page === n.label ? "page" : undefined} onClick={() => { setPage(n.label); setNotice(""); }}><Icon name={n.icon}/>{n.label}{page === n.label && <span className="nav-dot"/>}</button>)}</nav><div className="sidebar-bottom"><span className="workspace-avatar">P</span><div><strong>Pairadox team</strong><small>Hackathon workspace</small></div><span className="online-dot"/></div></aside>
    <main id="main" className="main-content">
      <header className="page-header"><div><div className="breadcrumb">Workspace <span>/</span> {page}</div><h1>{headings[page][0]}</h1><p>{headings[page][1]}</p></div><div className="header-actions"><span className="mode-pill"><i/>Demo workspace</span><button className="primary-button" disabled={!filtered.length || loading || !!error} onClick={() => { exportCsv(filtered, scenarios); setNotice(`Exported ${filtered.length} demo products from the current filters.`); }}><Icon name="download" size={17}/>Export demo CSV</button></div></header>
      <div className="demo-banner"><Icon name="shield" size={17}/><span><strong>Real product history. Illustrative recommendations.</strong> Planning figures and priority labels are examples until the backend is connected.</span><span className="snapshot-date">22 Sep 2026 snapshot</span></div>
      <div className="filter-bar"><div className="supplier-tabs" role="group" aria-label="Filter by supplier">{(["All suppliers", "IEK", "Systeme Electric"] as const).map(s => <button key={s} aria-pressed={supplier === s} className={supplier === s ? "selected" : ""} onClick={() => changeSupplier(s)}>{s}</button>)}</div><label className="search-box"><Icon name="search" size={18}/><span className="sr-only">Search products, SKUs or suppliers</span><input type="search" value={search} placeholder="Search products, SKUs or suppliers…" onChange={e => setSearch(e.target.value)}/></label></div>
      {notice && <p className="export-notice" role="status">{notice}</p>}
      {loading ? <div className="card state-card" role="status">Loading your workspace…</div> : error ? <div className="card state-card" role="alert"><h2>We couldn’t load the dashboard</h2><p>{error}</p><button className="primary-button" onClick={() => setAttempt(a => a + 1)}>Try again</button></div> : <>
      <div className="stats-grid"><div className="card stat"><span className="stat-icon"><Icon name="box" size={25}/></span><div><p>Products in view</p><strong>{filtered.length}<small> / {products.length} demo products</small></strong></div></div><div className="card stat"><span className="stat-icon amber"><Icon name="list" size={25}/></span><div><p>Needs attention <span className="tiny-label">Demo</span></p><strong>{attention}<small> sample priorities</small></strong></div></div><div className="card stat"><span className="stat-icon blue"><Icon name="truck" size={25}/></span><div><p>Suppliers in view</p><strong>{new Set(filtered.map(p => p.supplier)).size}<small> electrical supplies</small></strong></div></div></div>
      {page === "Data quality" ? <section className="card quality-card"><div className="card-heading"><div><h2>Before a number becomes an order</h2><p>Findings from the two supplier archives.</p></div><span className="source-tag">Source review</span></div><div className="quality-list">{[
        ["Needs confirmation", "Inventory dates are not interchangeable", "IEK monthly balances are opening balances. Systeme Electric also provides a dated purchasing worksheet with reserved and free stock. Confirm the meaning and date of each balance before integration."],
        ["Needs confirmation", "26 conflicting order multiples", "In Systeme Electric, 26 products show zero in the sales workbook and one in the MOQ workbook. Resolve the authoritative rule before rounding orders."],
        ["Review formula", "13 monthly columns divided by 12", "The Systeme Electric transit workbook sums September 2025–September 2026 as the last 12 months. That spans 13 columns and includes an unfinished month."],
        ["Missing input", "Customer IDs are not supplied", "Transaction exports identify documents, not customers. Customer-concentration explanations need another source; no customer-level anomaly claims are made here."],
        ["Preserved", "Blank cells and negative sales", "History charts preserve blank cells as missing and keep negative quantities. Their business meaning must be agreed; neither is silently converted to zero."],
        ["Demo only", "Forecasts and scenario adjustments", "The six-product preview uses illustrative planning inputs. No forecast accuracy, anomaly decision, or stockout probability has been established."],
      ].map(([status,title,body]) => <article className="quality-row" key={title}><span className="quality-status">{status}</span><div><h3>{title}</h3><p>{body}</p></div></article>)}</div></section> : <>
      {page === "Overview" && <section className="overview-callout"><div><span className="eyebrow">FROM HISTORY TO A DECISION</span><h2>Every recommendation should have a reason.</h2><p>Review inventory, explore demand, and see how assumptions change the suggested order.</p></div><button className="primary-button" onClick={() => setPage("Recommendations")}>Review recommendations<Icon name="arrow" size={17}/></button></section>}
      {!filtered.length ? <section className="card state-card"><Icon name="search" size={30}/><h2>No matching products</h2><p>Try a different name, SKU, or supplier.</p><button className="primary-button" onClick={() => { setSearch(""); setSupplier("All suppliers"); setSelectedSku(products[0]?.sku ?? null); }}>Clear filters</button></section> : page === "Sales history" ? <div className="history-page"><label className="product-selector">Choose a product<select value={historyProduct?.sku} onChange={e => setSelectedSku(e.target.value)}>{filtered.map(p => <option key={p.sku} value={p.sku}>{p.name} · {p.supplier}</option>)}</select></label>{historyProduct && <HistoryChart product={historyProduct}/>}</div> : <div className={`workspace-grid ${!selected ? "without-detail" : ""}`}><div className="workspace-left"><section className="card table-card"><div className="card-heading"><div><h2>Recommended orders</h2><p>Choose a product to explore its calculation.</p></div><span className="source-tag">{filtered.length} products</span></div><div className="table-scroll" role="region" aria-label="Recommendation table" tabIndex={0}><table><caption className="sr-only">Illustrative planning figures. Units shown per product.</caption><thead><tr><th scope="col">Product</th><th scope="col">Supplier</th><th scope="col" className="numeric">Available</th><th scope="col" className="numeric">Incoming</th><th scope="col" className="numeric">Order</th><th scope="col">Priority</th></tr></thead><tbody>{filtered.map(p => { const c = calculate(p, scenarios[p.sku] ?? defaultScenario); return <tr key={p.sku} className={selected?.sku === p.sku ? "selected-row" : ""}><th scope="row"><button className="product-button" aria-pressed={selected?.sku === p.sku} onClick={() => setSelectedSku(p.sku)}><ProductArt kind={p.kind}/><span><strong>{p.name}</strong><small>{p.sku} · {p.unit}</small></span></button></th><td><span className={`supplier-label ${p.supplier === "IEK" ? "iek" : ""}`}>{p.supplier}</span></td><td className="numeric">{number(c.available)}</td><td className="numeric">{number(p.incoming)}</td><td className="numeric order-cell">{number(c.order)}</td><td><span className={`priority priority-${p.priority}`}>{p.priority}</span></td></tr>; })}</tbody></table></div><div className="table-footer"><span><i className="small-dot"/>Sample planning figures · not purchase instructions</span><span>6-product preview</span></div></section>{historyProduct && <HistoryChart product={historyProduct}/>}</div>{selected && <Details key={selected.sku} product={selected} scenario={scenarios[selected.sku] ?? defaultScenario} setScenario={s => setScenarios(prev => ({ ...prev, [selected.sku]: s }))} onClose={() => setSelectedSku(null)}/>}</div>}
      </>}
      </>}
      <footer className="page-footer"><span>PAIRADOX <span className="footer-dot">·</span> Explainable inventory planning</span><span>IEK + Systeme Electric <span className="footer-dot">·</span> Backend not connected</span></footer>
    </main>
  </div>;
}
