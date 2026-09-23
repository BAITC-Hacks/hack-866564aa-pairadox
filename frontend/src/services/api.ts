export interface Recommendation {
  sku: string; monthly_forecast: number; lead_time_months: number;
  lead_time_demand: number; safety_stock: number; current_stock: number;
  goods_in_transit: number; raw_recommended_qty: number; recommended_qty: number;
  minimum_order_qty: number; order_multiple: number;
  urgency: string; risk: string; reason?: string; product_name?: string; unit?: string; supplier?: string;
}
export interface Product extends Recommendation { name: string; unit: string; supplier: string }
export interface History { points: { month: string; demand: number }[]; source: string; note: string }
export interface Scenario {
  apply_anomaly_exclusion: boolean; apply_stockout_correction: boolean;
  apply_seasonality: boolean; apply_growth_trend: boolean;
}
export const defaultScenario: Scenario = {
  apply_anomaly_exclusion: true, apply_stockout_correction: true,
  apply_seasonality: true, apply_growth_trend: true,
};
export interface Comparison {
  sku: string; monthly_forecast: number; recommended_qty: number;
  default_monthly_forecast: number; default_recommended_qty: number;
  recommended_qty_difference: number; urgency: string; risk: string;
}
const base = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');
export async function request<T>(path: string, signal: AbortSignal, method = 'GET'): Promise<T> {
  const response = await fetch(`${base}${path}`, { signal, method });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === 'string' ? body.detail : `Backend request failed (${response.status}).`);
  }
  const type = response.headers.get('content-type') || '';
  if (!type.includes('application/json')) throw new Error('Expected backend JSON. Check the API address and restart Vite.');
  return response.json();
}
const normalize = (sku: string) => String(sku).trim().replaceAll('_', '');
export async function loadProducts(signal: AbortSignal): Promise<Product[]> {
  const rows: Recommendation[] = [];
  for (let offset = 0; ; offset += 500) {
    const batch = await request<Recommendation[]>(`/recommendations?limit=500&offset=${offset}`, signal);
    if (!Array.isArray(batch)) throw new Error('Unexpected recommendation response.');
    rows.push(...batch);
    if (batch.length < 500) break;
  }
  return rows.map(r => {
    for (const key of ['monthly_forecast','lead_time_months','lead_time_demand','safety_stock','current_stock','goods_in_transit','raw_recommended_qty','recommended_qty','minimum_order_qty','order_multiple'] as const) {
      if (typeof r[key] !== 'number' || !Number.isFinite(r[key])) throw new Error(`Invalid ${key} for SKU ${r.sku}.`);
    }
    return { ...r, sku: String(r.sku), name: r.product_name || `SKU ${r.sku}`, unit: r.unit || 'source units', supplier: r.supplier || 'IEK' };
  });
}
export async function loadForecast(sku: string, signal: AbortSignal): Promise<History> {
  const detail = await request<{ forecasts: { forecast_month: string; forecast: number }[] }>(`/recommendations/${encodeURIComponent(sku)}`, signal);
  if (!Array.isArray(detail.forecasts)) throw new Error('Unexpected forecast response.');
  const points = detail.forecasts.map(row => {
    if (typeof row.forecast_month !== 'string' || typeof row.forecast !== 'number' || !Number.isFinite(row.forecast)) throw new Error('Invalid forecast values returned by backend.');
    return { month: row.forecast_month.slice(0, 7), demand: row.forecast };
  }).sort((a,b) => a.month.localeCompare(b.month));
  return { points, source: 'Backend forecast model', note: 'Predicted demand, not recorded sales. Historical monthly sales are not exposed by the current API.' };
}
export async function compareScenario(sku: string, scenario: Scenario, signal: AbortSignal) {
  const query = new URLSearchParams({ sku, ...Object.fromEntries(Object.entries(scenario).map(([k,v]) => [k,String(v)])) });
  const result = await request<{ results: Comparison[] }>(`/counterfactual?${query}`, signal, 'POST');
  const row = result.results.find(r => normalize(r.sku) === normalize(sku));
  if (!row || !Number.isFinite(row.recommended_qty) || !Number.isFinite(row.monthly_forecast)) throw new Error('No valid scenario result returned for this product.');
  return row;
}
