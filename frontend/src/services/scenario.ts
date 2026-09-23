import type { DashboardProduct, Scenario } from "../types/dashboard";

// Illustrative arithmetic only. The backend will own real recommendations.
export function calculate(p: DashboardProduct, s: Scenario) {
  const forecast = p.baseForecast
    + (s.seasonality ? p.seasonalUnits : 0)
    + (s.growth ? p.growthUnits : 0)
    + (s.stockout ? p.correctionUnits : 0);
  const available = p.stock - p.reserved;
  const net = Math.max(0, forecast + p.safetyStock - available - p.incoming);
  return { forecast, available, net, order: Math.ceil(net / p.orderMultiple) * p.orderMultiple };
}
