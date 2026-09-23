import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { compareScenario, defaultScenario, loadForecast, loadProducts } from "./services/api";
import type { Product, History, Scenario, Comparison } from "./services/api";
import "./App.css";
type Page = "Overview" | "Recommendations" | "Forecasts" | "Data quality";
type IconName = "grid" | "list" | "chart" | "shield" | "search" | "download" | "box" | "truck" | "arrow" | "close";
const nav: {label: Page; icon: IconName}[] = [{label:"Overview",icon:"grid"},{label:"Recommendations",icon:"list"},{label:"Forecasts",icon:"chart"},{label:"Data quality",icon:"shield"}];
const number = (n: number) => n.toLocaleString("en-US", {maximumFractionDigits: 2});
const message = (e: unknown) => e instanceof Error ? e.message : "Request failed.";
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

function ForecastChart({product}: {product: Product}) {
  const [data,setData] = useState<History | null>(null);
  const [error,setError] = useState('');
  const [attempt,setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setData(null); setError('');
    loadForecast(product.sku,controller.signal).then(d => {if(!controller.signal.aborted)setData(d)}).catch(e => {if(!controller.signal.aborted)setError(message(e))});
    return () => controller.abort();
  },[product.sku,attempt]);
  const points = data?.points ?? [];
  const min = Math.min(0,...points.map(p=>p.demand));
  const max = Math.max(1,...points.map(p=>p.demand));
  const x = (i:number) => 60+i*610/Math.max(1,points.length-1);
  const y = (v:number) => 180-(v-min)/(max-min)*145;
  return <section className="card history-card"><div className="card-heading"><div><h2>Forecasts</h2><p>{product.name} · {product.unit}</p></div><span className="source-tag">Backend data</span></div>
    {error ? <div className="state-card" role="alert"><p>{error}</p><button onClick={()=>setAttempt(a=>a+1)}>Retry forecast</button></div> : !data ? <p className="state-card" role="status">Loading forecast…</p> : !points.length ? <p className="state-card">No forecast available.</p> : <>
    <div className="chart-scroll"><svg className="history-chart" viewBox="0 0 710 225" role="img" aria-label={`Forecast demand for ${product.name}. Values available below.`}>
      {[0,1,2,3].map(i=>{const v=min+(max-min)*i/3;return <g key={i}><line x1="60" x2="670" y1={y(v)} y2={y(v)} stroke="#e8eef0"/><text x="52" y={y(v)+4} textAnchor="end">{number(v)}</text></g>})}
      <polyline points={points.map((p,i)=>`${x(i)},${y(p.demand)}`).join(' ')} fill="none" stroke="#008b7c" strokeWidth="2.5"/>
      {points.map((p,i)=><g key={p.month}><circle cx={x(i)} cy={y(p.demand)} r="3" fill="#008b7c"><title>{p.month}: {number(p.demand)}</title></circle>{(i%6===0||i===points.length-1)&&<text x={x(i)} y="208" textAnchor="middle">{p.month}</text>}</g>)}
    </svg></div><div className="chart-footer">{data.note}</div><details className="source-details"><summary>View values & source</summary><p>{data.source}</p><div className="values-grid">{points.map(p=><div key={p.month}><span>{p.month}</span><strong>{number(p.demand)}</strong></div>)}</div></details></>}
  </section>;
}

function Details({product:p,onClose}: {product:Product;onClose:()=>void}) {
  const [scenario,setScenario] = useState<Scenario>({...defaultScenario});
  const [result,setResult] = useState<Comparison|null>(null);
  const [busy,setBusy] = useState(false), [error,setError] = useState('');
  const active = useRef<AbortController|null>(null);
  useEffect(()=>()=>active.current?.abort(),[]);
  const labels: [keyof Scenario,string][] = [['apply_anomaly_exclusion','Exclude one-off anomalies'],['apply_stockout_correction','Stockout correction'],['apply_seasonality','Seasonality'],['apply_growth_trend','Growth trend']];
  function reset() {active.current?.abort();active.current=null;setBusy(false);setError('');setResult(null);setScenario({...defaultScenario})}
  async function compare() {
    active.current?.abort(); const controller=new AbortController(); active.current=controller;
    setBusy(true);setError('');setResult(null);
    try {const r=await compareScenario(p.sku,scenario,controller.signal);if(!controller.signal.aborted)setResult(r)}
    catch(e){if(!controller.signal.aborted)setError(message(e))}
    finally {if(!controller.signal.aborted)setBusy(false)}
  }
  return <aside className="card detail-card"><div className="detail-top"><span className="eyebrow">THE DECISION, EXPLAINED</span><button className="icon-button" onClick={onClose} aria-label="Close product details"><Icon name="close"/></button></div>
    <h2>Why order {number(p.recommended_qty)}?</h2><p className="detail-product">{p.name}</p><p className="sku-line">{p.sku} · {p.unit}</p>
    <div className="example-note">Default backend calculation<span>Lead time: {number(p.lead_time_months)} months · Risk: {p.risk} (heuristic)</span></div>
    <dl className="breakdown"><div><dt>Monthly forecast</dt><dd>{number(p.monthly_forecast)}</dd></div><div><dt>Demand during lead time</dt><dd>{number(p.lead_time_demand)}</dd></div><div><dt>Safety stock</dt><dd>+{number(p.safety_stock)}</dd></div><div><dt>Current stock</dt><dd>−{number(p.current_stock)}</dd></div><div><dt>Goods in transit</dt><dd>−{number(p.goods_in_transit)}</dd></div><div className="subtotal"><dt>Net requirement <small>Minimum zero</small></dt><dd>{number(p.raw_recommended_qty)}</dd></div><div><dt>Minimum order</dt><dd>{number(p.minimum_order_qty)}</dd></div><div><dt>Order multiple</dt><dd>{number(p.order_multiple)}</dd></div></dl>
    <div className="order-total"><span>Recommended order</span><strong>{number(p.recommended_qty)} <small>{p.unit}</small></strong></div>
    {p.reason&&<p className="rounding-note">{p.reason}</p>}
    <div className="scenario-heading"><h3>Compare a scenario</h3><button className="text-button" onClick={reset}>Reset</button></div>
    <div className="toggles">{labels.map(([key,label])=><label className="toggle-row" key={key}><span><strong>{label}</strong></span><input type="checkbox" disabled={busy} checked={scenario[key]} onChange={e=>{setScenario(s=>({...s,[key]:e.target.checked}));setResult(null);setError('')}}/><span className="switch" aria-hidden="true"/></label>)}</div>
    <button className="primary-button" disabled={busy} onClick={compare}>{busy?'Recalculating…':'Calculate scenario'}</button>
    <p className="detail-foot">The engine recalculates the full dataset. This may take a while. The table and CSV retain the default calculation.</p>
    {busy&&<p role="status">Waiting for the forecasting engine…</p>}{error&&<p role="alert">{error}</p>}
    {result&&<div className="example-note" role="status"><strong>Scenario order: {number(result.recommended_qty)} {p.unit}</strong><span>Default: {number(result.default_recommended_qty)} · Difference: {number(result.recommended_qty_difference)}</span><span>Monthly forecast: {number(result.monthly_forecast)} · Priority: {result.urgency}</span><span>The breakdown above describes the default calculation.</span></div>}
  </aside>;
}

function exportCsv(products:Product[]) {
  const cell=(v:string|number)=>{let s=String(v);if(/^[=+\-@\t\r]/.test(s))s=`'${s}`;return `"${s.replaceAll('"','""')}"`};
  const rows:(string|number)[][]=[['Mode','SKU','Product','Supplier','Unit','Current stock','In transit','Monthly forecast','Safety stock','Order multiple','Recommended order','Priority','Risk']];
  products.forEach(p=>rows.push(['Backend default',p.sku,p.name,p.supplier,p.unit,p.current_stock,p.goods_in_transit,p.monthly_forecast,p.safety_stock,p.order_multiple,p.recommended_qty,p.urgency,p.risk]));
  const url=URL.createObjectURL(new Blob(['\uFEFF'+rows.map(r=>r.map(cell).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8;'}));
  const a=document.createElement('a');a.href=url;a.download='pairadox-recommendations.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}

export default function App() {
  const [page,setPage]=useState<Page>('Recommendations');
  const [products,setProducts]=useState<Product[]>([]);
  const [loading,setLoading]=useState(true),[error,setError]=useState('');
  const [attempt,setAttempt]=useState(0),[search,setSearch]=useState('');
  const [selectedSku,setSelectedSku]=useState<string|null>(null);
  const [pageIndex,setPageIndex]=useState(0),[notice,setNotice]=useState('');
  useEffect(()=>{const controller=new AbortController();setLoading(true);setError('');
    loadProducts(controller.signal).then(data=>{if(!controller.signal.aborted){setProducts(data);setSelectedSku(data[0]?.sku??null);setPageIndex(0)}}).catch(e=>{if(!controller.signal.aborted)setError(message(e))}).finally(()=>{if(!controller.signal.aborted)setLoading(false)});
    return ()=>controller.abort();
  },[attempt]);
  const query=search.trim().toLowerCase();
  const filtered=products.filter(p=>[p.name,p.sku,p.supplier].some(s=>s.toLowerCase().includes(query)));
  const selected=filtered.find(p=>p.sku===selectedSku);
  const historyProduct=selected??filtered[0];
  const visible=filtered.slice(pageIndex*50,(pageIndex+1)*50);
  const attention=filtered.filter(p=>p.recommended_qty>0&&p.urgency!=='low').length;
  return <div className="app-shell"><a className="skip-link" href="#main">Skip to content</a><aside className="sidebar"><a className="wordmark" href="#main">PAIRADO<span>X</span><i/></a><p className="nav-caption">PURCHASING WORKSPACE</p><nav aria-label="Main navigation">{nav.map(n=><button key={n.label} className={`nav-item ${page===n.label?'active':''}`} aria-current={page===n.label?'page':undefined} onClick={()=>setPage(n.label)}><Icon name={n.icon}/>{n.label}</button>)}</nav><div className="sidebar-bottom"><span className="workspace-avatar">P</span><div><strong>Pairadox team</strong><small>Hackathon workspace</small></div></div></aside>
    <main id="main" className="main-content"><header className="page-header"><div><div className="breadcrumb">Workspace / {page}</div><h1>{page==='Overview'?'Your purchasing workspace':page==='Recommendations'?'Purchase recommendations':page==='Forecasts'?'Expected demand ahead':'Know what the data can tell you'}</h1><p>Explainable inventory planning from the supplied IEK data.</p></div><div className="header-actions"><span className="mode-pill"><i/>{loading?'Connecting…':error?'Unavailable':'Backend connected'}</span><button className="primary-button" disabled={loading||!!error||!filtered.length} onClick={()=>{exportCsv(filtered);setNotice(`Exported ${filtered.length} default recommendations.`)}}><Icon name="download"/>Export CSV</button></div></header>
    <div className="demo-banner"><Icon name="shield"/><span><strong>Backend calculations · IEK.</strong> Workbook snapshots, not live stock. Names and units appear only when supplied by the API; otherwise products are identified by SKU.</span></div>
    <div className="filter-bar"><span className="source-tag">IEK dataset</span><label className="search-box"><Icon name="search"/><span className="sr-only">Search products</span><input type="search" placeholder="Search products, SKUs or suppliers…" value={search} onChange={e=>{setSearch(e.target.value);setPageIndex(0)}}/></label></div>
    {notice&&<p role="status" className="export-notice">{notice}</p>}
    {loading?<div className="card state-card" role="status">Loading recommendations from the backend. The first calculation may take several minutes…</div>:error?<div className="card state-card" role="alert"><h2>Backend unavailable</h2><p>{error}</p><p>Start the Python backend on port 8000, then retry. No demo numbers are substituted.</p><button className="primary-button" onClick={()=>setAttempt(a=>a+1)}>Try again</button></div>:<>
    <div className="stats-grid">{[['Products in view',filtered.length,`of ${products.length} products`],['Needs attention',attention,'non-low priority orders'],['Suppliers in view',new Set(filtered.map(p=>p.supplier)).size,'connected dataset']].map(([label,value,caption])=><div className="card stat" key={label}><span className="stat-icon"><Icon name="box"/></span><div><p>{label}</p><strong>{value}<small> {caption}</small></strong></div></div>)}</div>
    {page==='Data quality'?<section className="card quality-card"><div className="card-heading"><h2>Assumptions behind these results</h2></div><div className="quality-list">{[
      ['Scope','IEK only','This backend processes the supplied IEK workbooks. Systeme Electric integration is still pending.'],
      ['API coverage','Product labels and historical sales','The current API does not expose a catalog or monthly sales history. Missing names are shown as SKUs and missing units as source units. The Forecasts chart shows predicted demand.'],
      ['Planning','Lead time and service level','The backend defaults to one month lead time and a 95% service-level input. These are planning assumptions, not measured supplier performance.'],
      ['Inventory','Snapshot and transit timing','Current stock comes from the inventory workbook. Transit quantities are summed by the backend; this view does not verify arrival dates against lead time.'],
      ['Data','Source normalization','Monthly blank cells are converted to zero. Negative monthly sales are preserved, while transaction quantities are converted to absolute values for forecasting. The latest month may be incomplete.'],
      ['Interpretation','Priority and risk','Priority and risk are backend heuristics. Risk is not a calibrated stockout probability; forecast accuracy has not been established by this integration.'],
      ['Scenarios','Default versus comparison','Scenario switches call the forecasting engine. Comparison results are shown separately; the main table and CSV continue to show the default model.'],
    ].map(([status,title,body])=><article className="quality-row" key={title}><span className="quality-status">{status}</span><div><h3>{title}</h3><p>{body}</p></div></article>)}</div></section>:!filtered.length?<section className="card state-card"><h2>No matching recommendations</h2><p>Try another search, or check the backend dataset.</p></section>:page==='Forecasts'?<div className="history-page"><label className="product-selector">Choose a product<select value={historyProduct?.sku} onChange={e=>setSelectedSku(e.target.value)}>{filtered.map(p=><option key={p.sku} value={p.sku}>{p.name} · {p.sku}</option>)}</select></label>{historyProduct&&<ForecastChart key={historyProduct.sku} product={historyProduct}/>}</div>:<>
    {page==='Overview'&&<section className="overview-callout"><div><span className="eyebrow">FROM HISTORY TO A DECISION</span><h2>Every recommendation should have a reason.</h2><p>Select a product to inspect its forecast, inventory and order rules.</p></div><button className="primary-button" onClick={()=>setPage('Recommendations')}>Review recommendations<Icon name="arrow"/></button></section>}
    <div className={`workspace-grid ${selected?'':'without-detail'}`}><div className="workspace-left"><section className="card table-card"><div className="card-heading"><div><h2>Recommended orders</h2><p>Default backend calculation · quantities use each product’s unit.</p></div><span className="source-tag">{filtered.length} products</span></div><div className="table-scroll" tabIndex={0} role="region" aria-label="Recommendation table"><table><thead><tr><th>Product</th><th>Supplier</th><th className="numeric">Stock</th><th className="numeric">In transit</th><th className="numeric">Order</th><th>Priority</th></tr></thead><tbody>{visible.map(p=><tr key={p.sku} className={selected?.sku===p.sku?'selected-row':''}><th scope="row"><button className="product-button" onClick={()=>setSelectedSku(p.sku)} aria-pressed={selected?.sku===p.sku}><span className="stat-icon"><Icon name="box"/></span><span><strong>{p.name}</strong><small>{p.sku} · {p.unit}</small></span></button></th><td>{p.supplier}</td><td className="numeric">{number(p.current_stock)}</td><td className="numeric">{number(p.goods_in_transit)}</td><td className="numeric order-cell">{number(p.recommended_qty)}</td><td><span className={`priority priority-${p.urgency}`}>{p.urgency}</span></td></tr>)}</tbody></table></div><div className="table-footer"><button disabled={pageIndex===0} onClick={()=>setPageIndex(i=>i-1)}>Previous</button><span>Page {pageIndex+1} of {Math.ceil(filtered.length/50)}</span><button disabled={(pageIndex+1)*50>=filtered.length} onClick={()=>setPageIndex(i=>i+1)}>Next</button></div></section>{historyProduct&&<ForecastChart key={historyProduct.sku} product={historyProduct}/>}</div>{selected&&<Details key={selected.sku} product={selected} onClose={()=>setSelectedSku(null)}/>}</div></>}
    </>}
    <footer className="page-footer"><span>PAIRADOX · Explainable inventory planning</span><span>IEK · {loading?'Connecting':error?'Connection error':'Backend calculations'}</span></footer></main></div>;
}
