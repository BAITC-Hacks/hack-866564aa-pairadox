import { useState } from "react";
import RecommendationTable from "./components/RecommendationTable";
import { mockRecommendations } from "./data/mockRecommendations";
import "./App.css";

export default function App() {
  const [search, setSearch] = useState("");
  const query = search.trim().toLowerCase();

  const filtered = mockRecommendations.filter((item) =>
    [item.sku, item.product_name, item.supplier].some((value) =>
      value.toLowerCase().includes(query),
    ),
  );

  return (
    <main className="dashboard">
      <header>
        <p className="eyebrow">PAIRADOX · INVENTORY PLANNING</p>
        <h1>Purchase recommendations</h1>
        <p>Review what to order before your next replenishment.</p>
        <span className="demo-label">Demo data · Backend not connected</span>
      </header>

      <section aria-label="Recommendations">
        <div className="toolbar">
          <div>
            <h2>Recommended orders</h2>
            <p aria-live="polite">
              {filtered.length} of {mockRecommendations.length} products
            </p>
          </div>

          <div className="search-field">
            <label htmlFor="search">Search products</label>
            <input
              id="search"
              type="search"
              placeholder="SKU, product, or supplier"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
        </div>

        <RecommendationTable recommendations={filtered} />
      </section>
    </main>
  );
}