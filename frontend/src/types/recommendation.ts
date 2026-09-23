export interface Recommendation {
  sku: string;
  product_name: string;
  supplier: string;
  current_stock: number;
  in_transit: number;
  forecast: number;
  safety_stock: number;
  recommended_qty: number;
  urgency: "critical" | "high" | "medium" | "low";
  stockout_risk: number; // 0–1
  seasonality_factor: number;
  growth_factor: number;
  stockout_correction: number;
  excluded_outliers: {
    client_id: string;
    quantity: number;
    reason: string;
  }[];
  explanation: string[];
}