import math

import numpy as np
import pandas as pd


SERVICE_LEVEL_Z = {
    0.90: 1.282,
    0.95: 1.645,
    0.975: 1.960,
    0.99: 2.326,
}


# ============================================================
# HELPERS
# ============================================================

def safe_number(
    value,
    default: float = 0.0,
) -> float:
    """
    Convert value to a finite float.

    None, NaN and infinity are replaced by default.
    """

    try:
        if value is None or pd.isna(value):
            return float(default)

        value = float(value)

        if not math.isfinite(value):
            return float(default)

        return value

    except (TypeError, ValueError):
        return float(default)


def safe_non_negative(
    value,
    default: float = 0.0,
) -> float:
    """
    Convert value to a non-negative float.
    """

    return max(
        0.0,
        safe_number(
            value,
            default=default,
        ),
    )


def get_z_score(
    service_level: float = 0.95,
) -> float:
    """
    Return z-score for the requested service level.

    Supported values:
        0.90
        0.95
        0.975
        0.99

    Unsupported values fall back to 95%.
    """

    service_level = safe_number(
        service_level,
        default=0.95,
    )

    return SERVICE_LEVEL_Z.get(
        service_level,
        SERVICE_LEVEL_Z[0.95],
    )


# ============================================================
# DEMAND DURING LEAD TIME
# ============================================================

def calculate_lead_time_demand(
    monthly_forecast: float,
    lead_time_months: float,
) -> float:
    """
    Calculate expected demand while waiting for supplier.

    Example:

        monthly_forecast = 100
        lead_time_months = 1.5

        result = 150
    """

    monthly_forecast = safe_non_negative(
        monthly_forecast
    )

    lead_time_months = safe_non_negative(
        lead_time_months,
        default=1.0,
    )

    return float(
        monthly_forecast
        * lead_time_months
    )


# ============================================================
# SAFETY STOCK
# ============================================================

def calculate_safety_stock(
    demand_std: float,
    lead_time_months: float,
    service_level: float = 0.95,
) -> float:
    """
    Calculate safety stock.

    Formula:

        safety_stock =
            z
            * demand_std
            * sqrt(lead_time_months)

    Assumption:
        demand_std is standard deviation of MONTHLY demand.
    """

    demand_std = safe_non_negative(
        demand_std
    )

    lead_time_months = safe_non_negative(
        lead_time_months,
        default=1.0,
    )

    if (
        demand_std == 0
        or lead_time_months == 0
    ):
        return 0.0

    z = get_z_score(
        service_level
    )

    safety_stock = (
        z
        * demand_std
        * math.sqrt(
            lead_time_months
        )
    )

    return float(
        max(
            0.0,
            safety_stock,
        )
    )


# ============================================================
# INVENTORY POSITION
# ============================================================

def calculate_inventory_position(
    current_stock: float,
    goods_in_transit: float = 0.0,
) -> float:
    """
    Inventory available or already expected.

    inventory_position =
        current_stock
        + goods_in_transit
    """

    current_stock = safe_non_negative(
        current_stock
    )

    goods_in_transit = safe_non_negative(
        goods_in_transit
    )

    return float(
        current_stock
        + goods_in_transit
    )


# ============================================================
# RAW REPLENISHMENT REQUIREMENT
# ============================================================

def calculate_raw_reorder_quantity(
    lead_time_demand: float,
    safety_stock: float,
    current_stock: float,
    goods_in_transit: float = 0.0,
) -> float:
    """
    Core procurement formula.

    raw_order =
        lead_time_demand
        + safety_stock
        - current_stock
        - goods_in_transit

    Negative recommendations are converted to zero.
    """

    lead_time_demand = safe_non_negative(
        lead_time_demand
    )

    safety_stock = safe_non_negative(
        safety_stock
    )

    current_stock = safe_non_negative(
        current_stock
    )

    goods_in_transit = safe_non_negative(
        goods_in_transit
    )

    quantity = (
        lead_time_demand
        + safety_stock
        - current_stock
        - goods_in_transit
    )

    return float(
        max(
            0.0,
            quantity,
        )
    )


# ============================================================
# SUPPLIER CONSTRAINTS
# ============================================================

def apply_supplier_constraints(
    quantity: float,
    minimum_order_qty: float = 0.0,
    order_multiple: float = 1.0,
) -> float:
    """
    Apply supplier constraints.

    IMPORTANT:

    minimum_order_qty:
        Minimum total amount that may be ordered.

        Example:
            required = 12
            minimum = 20

            result = 20

    order_multiple:
        Quantity must be ordered in multiples.

        Example:
            required = 53
            multiple = 20

            result = 60

    They are NOT the same concept.
    """

    quantity = safe_non_negative(
        quantity
    )

    minimum_order_qty = safe_non_negative(
        minimum_order_qty
    )

    order_multiple = safe_non_negative(
        order_multiple,
        default=1.0,
    )

    if quantity <= 0:
        return 0.0

    # Apply minimum order quantity.
    if (
        minimum_order_qty > 0
        and quantity < minimum_order_qty
    ):
        quantity = minimum_order_qty

    # Apply order multiple.
    if order_multiple > 0:
        quantity = (
            math.ceil(
                quantity
                / order_multiple
            )
            * order_multiple
        )

    return float(quantity)


def round_to_moq(
    quantity: float,
    moq: float,
) -> float:
    """
    Backward-compatible helper.

    In the old code `moq` was treated as an order multiple.

    Keep this function so other modules do not break.

    Prefer apply_supplier_constraints() in new code.
    """

    return apply_supplier_constraints(
        quantity=quantity,
        minimum_order_qty=0.0,
        order_multiple=moq,
    )


# ============================================================
# COVERAGE
# ============================================================

def calculate_stock_coverage_months(
    current_stock: float,
    monthly_forecast: float,
) -> float:
    """
    Number of months that CURRENT stock can cover.
    """

    current_stock = safe_non_negative(
        current_stock
    )

    monthly_forecast = safe_non_negative(
        monthly_forecast
    )

    if monthly_forecast <= 0:
        return np.inf

    return float(
        current_stock
        / monthly_forecast
    )


def calculate_inventory_position_coverage(
    current_stock: float,
    goods_in_transit: float,
    monthly_forecast: float,
) -> float:
    """
    Number of months covered by:

        current stock
        + goods already in transit
    """

    monthly_forecast = safe_non_negative(
        monthly_forecast
    )

    if monthly_forecast <= 0:
        return np.inf

    inventory_position = (
        calculate_inventory_position(
            current_stock=current_stock,
            goods_in_transit=goods_in_transit,
        )
    )

    return float(
        inventory_position
        / monthly_forecast
    )


# ============================================================
# URGENCY
# ============================================================

def classify_urgency(
    recommended_qty: float,
    inventory_position_coverage_months: float,
    lead_time_months: float,
) -> str:
    """
    Determine procurement urgency.

    Unlike the previous implementation,
    this uses inventory position:

        current stock + goods in transit

    rather than current stock alone.

    critical:
        available inventory position does not cover lead time

    high:
        coverage is only slightly above lead time

    medium:
        order is needed but there is more buffer

    low:
        no order is currently required
    """

    recommended_qty = safe_non_negative(
        recommended_qty
    )

    if recommended_qty <= 0:
        return "low"

    lead_time_months = safe_non_negative(
        lead_time_months,
        default=1.0,
    )

    if (
        inventory_position_coverage_months
        is None
    ):
        coverage = 0.0

    else:
        try:
            coverage = float(
                inventory_position_coverage_months
            )
        except (TypeError, ValueError):
            coverage = 0.0

    if math.isinf(coverage):
        return "low"

    if coverage < lead_time_months:
        return "critical"

    if coverage < (
        lead_time_months + 0.5
    ):
        return "high"

    return "medium"


# ============================================================
# RECOMMENDATION RISK
# ============================================================

def classify_risk(
    coefficient_of_variation: float,
    stockout_risk: bool = False,
    structural_shift: bool = False,
) -> str:
    """
    Estimate uncertainty of recommendation.

    This is NOT procurement urgency.

    It describes how uncertain the recommendation is.

    Signals:
        demand variability
        reconstructed stockout demand
        structural demand shift
    """

    cv = safe_non_negative(
        coefficient_of_variation
    )

    score = 0

    if cv >= 1.0:
        score += 2

    elif cv >= 0.5:
        score += 1

    if bool(stockout_risk):
        score += 1

    if bool(structural_shift):
        score += 1

    if score >= 3:
        return "high"

    if score >= 1:
        return "medium"

    return "low"


# ============================================================
# ONE SKU
# ============================================================

def calculate_recommendation(
    sku: str,
    monthly_forecast: float,
    demand_std: float,
    current_stock: float,
    goods_in_transit: float = 0.0,
    minimum_order_qty: float = 0.0,
    order_multiple: float = 1.0,
    lead_time_months: float = 1.0,
    service_level: float = 0.95,
    coefficient_of_variation: float = 0.0,
    stockout_risk: bool = False,
    structural_shift: bool = False,
) -> dict:
    """
    Calculate complete procurement recommendation
    for one SKU.
    """

    sku = str(sku)

    monthly_forecast = safe_non_negative(
        monthly_forecast
    )

    demand_std = safe_non_negative(
        demand_std
    )

    current_stock = safe_non_negative(
        current_stock
    )

    goods_in_transit = safe_non_negative(
        goods_in_transit
    )

    minimum_order_qty = safe_non_negative(
        minimum_order_qty
    )

    order_multiple = safe_non_negative(
        order_multiple,
        default=1.0,
    )

    lead_time_months = safe_non_negative(
        lead_time_months,
        default=1.0,
    )

    coefficient_of_variation = (
        safe_non_negative(
            coefficient_of_variation
        )
    )

    # --------------------------------------------------------
    # 1. Demand expected during supplier lead time
    # --------------------------------------------------------

    lead_time_demand = (
        calculate_lead_time_demand(
            monthly_forecast=
                monthly_forecast,
            lead_time_months=
                lead_time_months,
        )
    )

    # --------------------------------------------------------
    # 2. Safety stock
    # --------------------------------------------------------

    safety_stock = (
        calculate_safety_stock(
            demand_std=demand_std,
            lead_time_months=
                lead_time_months,
            service_level=
                service_level,
        )
    )

    # --------------------------------------------------------
    # 3. Inventory position
    # --------------------------------------------------------

    inventory_position = (
        calculate_inventory_position(
            current_stock=
                current_stock,
            goods_in_transit=
                goods_in_transit,
        )
    )

    # --------------------------------------------------------
    # 4. Raw requirement
    # --------------------------------------------------------

    raw_recommended_qty = (
        calculate_raw_reorder_quantity(
            lead_time_demand=
                lead_time_demand,
            safety_stock=
                safety_stock,
            current_stock=
                current_stock,
            goods_in_transit=
                goods_in_transit,
        )
    )

    # --------------------------------------------------------
    # 5. Supplier constraints
    # --------------------------------------------------------

    recommended_qty = (
        apply_supplier_constraints(
            quantity=
                raw_recommended_qty,
            minimum_order_qty=
                minimum_order_qty,
            order_multiple=
                order_multiple,
        )
    )

    # --------------------------------------------------------
    # 6. Current-stock coverage
    # --------------------------------------------------------

    stock_coverage = (
        calculate_stock_coverage_months(
            current_stock=
                current_stock,
            monthly_forecast=
                monthly_forecast,
        )
    )

    # --------------------------------------------------------
    # 7. Coverage including goods in transit
    # --------------------------------------------------------

    position_coverage = (
        calculate_inventory_position_coverage(
            current_stock=
                current_stock,
            goods_in_transit=
                goods_in_transit,
            monthly_forecast=
                monthly_forecast,
        )
    )

    # --------------------------------------------------------
    # 8. Urgency
    # --------------------------------------------------------

    urgency = classify_urgency(
        recommended_qty=
            recommended_qty,
        inventory_position_coverage_months=
            position_coverage,
        lead_time_months=
            lead_time_months,
    )

    # --------------------------------------------------------
    # 9. Recommendation uncertainty
    # --------------------------------------------------------

    risk = classify_risk(
        coefficient_of_variation=
            coefficient_of_variation,
        stockout_risk=
            stockout_risk,
        structural_shift=
            structural_shift,
    )

    # --------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------

    return {
        "sku": sku,

        "monthly_forecast":
            float(monthly_forecast),

        "lead_time_months":
            float(lead_time_months),

        "lead_time_demand":
            float(lead_time_demand),

        "demand_std":
            float(demand_std),

        "safety_stock":
            float(safety_stock),

        "current_stock":
            float(current_stock),

        "goods_in_transit":
            float(goods_in_transit),

        "inventory_position":
            float(inventory_position),

        "raw_recommended_qty":
            float(raw_recommended_qty),

        "minimum_order_qty":
            float(minimum_order_qty),

        "order_multiple":
            float(order_multiple),

        "recommended_qty":
            float(recommended_qty),

        "stock_coverage_months":
            (
                None
                if np.isinf(
                    stock_coverage
                )
                else float(
                    stock_coverage
                )
            ),

        "inventory_position_coverage_months":
            (
                None
                if np.isinf(
                    position_coverage
                )
                else float(
                    position_coverage
                )
            ),

        "urgency":
            urgency,

        "risk":
            risk,

        "has_stockout_risk":
            bool(stockout_risk),

        "has_structural_shift":
            bool(structural_shift),
    }


