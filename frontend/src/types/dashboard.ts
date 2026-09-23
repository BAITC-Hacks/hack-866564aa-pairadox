export type Supplier = "IEK" | "Systeme Electric";
export type Priority = "high" | "medium" | "low";
export interface DashboardProduct {
  sku: string;
  name: string;
  sourceName: string;
  supplier: Supplier;
  kind: "socket" | "breaker" | "box" | "cable" | "switch" | "light";
  unit: "pcs" | "m";
  stock: number;
  reserved: number;
  incoming: number;
  baseForecast: number;
  seasonalUnits: number;
  growthUnits: number;
  correctionUnits: number;
  safetyStock: number;
  orderMultiple: number;
  arrivalDate: string;
  priority: Priority;
  history: { month: string; quantity: number | null }[];
  sourceFile: string;
  sourceSheet: string;
  sourceRow: number;
  orderRuleNote: string;
}
export interface Scenario {
  seasonality: boolean;
  growth: boolean;
  stockout: boolean;
}
