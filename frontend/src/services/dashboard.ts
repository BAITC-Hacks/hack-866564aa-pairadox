import type { DashboardProduct } from "../types/dashboard";

// Replace this adapter with the agreed backend response mapping when it is ready.
// Keep the separate UI model: this file does not change Farida's API contract.
export async function loadDashboard(): Promise<DashboardProduct[]> {
  const { dashboardProducts } = await import("../data/dashboardDemo");
  return dashboardProducts;
}
