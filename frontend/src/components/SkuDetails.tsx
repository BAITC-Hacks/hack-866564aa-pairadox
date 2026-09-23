import type { Recommendation } from "../types/recommendation";

interface Props {
  recommendation: Recommendation;
  onClose: () => void;
}

export default function SkuDetails({
  recommendation: item,
  onClose,
}: Props) {
  return (
    <section className="sku-details" aria-labelledby="details-title">
      <div className="details-heading">
        <div>
          <p className="eyebrow">RECOMMENDATION BREAKDOWN</p>
          <h2 id="details-title">
            {item.sku} · {item.product_name}
          </h2>
          <p>{item.supplier} · Demo data</p>
        </div>
        <button type="button" onClick={onClose}>
          Close details
        </button>
      </div>

      <dl className="calculation">
        <div>
          <dt>Forecast</dt>
          <dd>{item.forecast}</dd>
        </div>
        <div>
          <dt>+ Safety stock</dt>
          <dd>{item.safety_stock}</dd>
        </div>
        <div>
          <dt>− Current stock</dt>
          <dd>{item.current_stock}</dd>
        </div>
        <div>
          <dt>− In transit</dt>
          <dd>{item.in_transit}</dd>
        </div>
        <div className="calculation-total">
          <dt>Recommended order</dt>
          <dd>{item.recommended_qty} units</dd>
        </div>
      </dl>

      <p>Order quantities have a minimum of zero.</p>

      <h3>Why this recommendation?</h3>
      {item.explanation.length > 0 ? (
        <ul>
          {item.explanation.map((reason, index) => (
            <li key={`${item.sku}-${index}`}>{reason}</li>
          ))}
        </ul>
      ) : (
        <p>No explanation available.</p>
      )}

      <h3>Excluded orders</h3>
      {item.excluded_outliers.length > 0 ? (
        <ul>
          {item.excluded_outliers.map((order, index) => (
            <li key={`${order.client_id}-${index}`}>
              Client {order.client_id}: {order.quantity} units — {order.reason}
            </li>
          ))}
        </ul>
      ) : (
        <p>No orders excluded.</p>
      )}
    </section>
  );
}