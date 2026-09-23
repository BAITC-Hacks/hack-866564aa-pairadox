import type { Recommendation } from "../types/recommendation";

interface Props {
  recommendations: Recommendation[];
  onSelect: (recommendation: Recommendation) => void;
}

export default function RecommendationTable({
  recommendations,
  onSelect,
}: Props) {
  return (
    <div
      className="table-container"
      role="region"
      aria-label="Recommendation table"
      tabIndex={0}
    >
      <table>
        <caption>Suggested replenishment quantities — demo data</caption>
        <thead>
          <tr>
            <th scope="col">SKU</th>
            <th scope="col">Product</th>
            <th scope="col">Supplier</th>
            <th scope="col">Stock</th>
            <th scope="col">In transit</th>
            <th scope="col">Forecast</th>
            <th scope="col">Order qty</th>
            <th scope="col">Urgency</th>
          </tr>
        </thead>

        <tbody>
          {recommendations.map((item) => (
            <tr key={item.sku}>
              <th scope="row">
  <button
    type="button"
    className="sku-button"
    onClick={() => onSelect(item)}
    aria-label={`View recommendation for ${item.sku}`}
  >
    {item.sku}
  </button>
</th>
              <td>{item.product_name}</td>
              <td>{item.supplier}</td>
              <td>{item.current_stock}</td>
              <td>{item.in_transit}</td>
              <td>{item.forecast}</td>
              <td className="order-quantity">{item.recommended_qty}</td>
              <td>
                <span className={`badge badge-${item.urgency}`}>
                  {item.urgency}
                </span>
              </td>
            </tr>
          ))}

          {recommendations.length === 0 && (
            <tr>
              <td colSpan={8}>No recommendations match your search.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}