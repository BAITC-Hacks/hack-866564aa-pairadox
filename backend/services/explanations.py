import math

import numpy as np
import pandas as pd


def safe_float(value, default: float = 0.0) -> float:
    """
    Convert a value to a finite float.

    NaN, None and infinity are replaced with default.
    """

    if value is None or pd.isna(value):
        return float(default)

    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(default)

    if not math.isfinite(number):
        return float(default)

    return number


def safe_bool(value) -> bool:
    """
    Convert common values to boolean safely.
    """

    if value is None:
        return False

    if isinstance(value, (bool, np.bool_)):
        return bool(value)

    if isinstance(value, str):
        return value.strip().lower() in {
            "true",
            "1",
            "yes",
            "y",
        }

    try:
        return bool(value)
    except Exception:
        return False


def build_formula_explanation(
    lead_time_demand: float,
    safety_stock: float,
    current_stock: float,
    goods_in_transit: float,
    raw_recommended_qty: float,
    recommended_qty: float,
    moq: float,
) -> dict:
    """
    Explain the core replenishment formula.

    Formula:

    recommended =
        lead_time_demand
        + safety_stock
        - current_stock
        - goods_in_transit
    """

    lead_time_demand = safe_float(lead_time_demand)
    safety_stock = safe_float(safety_stock)
    current_stock = safe_float(current_stock)
    goods_in_transit = safe_float(goods_in_transit)
    raw_recommended_qty = safe_float(raw_recommended_qty)
    recommended_qty = safe_float(recommended_qty)
    moq = max(1.0, safe_float(moq, default=1.0))

    formula = (
        f"{lead_time_demand:.1f} "
        f"+ {safety_stock:.1f} "
        f"- {current_stock:.1f} "
        f"- {goods_in_transit:.1f} "
        f"= {raw_recommended_qty:.1f}"
    )

    if recommended_qty > raw_recommended_qty:
        rounding = (
            f"raw requirement {raw_recommended_qty:.1f} "
            f"was rounded up to {recommended_qty:.1f} "
            f"using supplier order multiple {moq:.1f}"
        )
    elif raw_recommended_qty <= 0:
        rounding = "no replenishment is currently required"
    else:
        rounding = "no additional MOQ rounding was required"

    return {
        "formula": formula,
        "rounding_explanation": rounding,
    }


def build_forecast_factors(
    baseline_demand: float | None = None,
    growth_factor: float | None = None,
    trend_class: str | None = None,
    seasonal_factor: float | None = None,
    seasonality_source: str | None = None,
) -> list[str]:
    """
    Build explanations for forecast-related factors.
    """

    factors = []

    if baseline_demand is not None and not pd.isna(baseline_demand):
        baseline = safe_float(baseline_demand)

        factors.append(
            f"recent baseline demand is {baseline:.1f} units/month"
        )

    if growth_factor is not None and not pd.isna(growth_factor):
        growth = safe_float(growth_factor, default=1.0)

        growth_percent = (growth - 1.0) * 100

        if growth_percent >= 5:
            factors.append(
                f"sustained demand growth contributes "
                f"+{growth_percent:.1f}%"
            )

        elif growth_percent <= -5:
            factors.append(
                f"recent demand trend contributes "
                f"{growth_percent:.1f}%"
            )

        else:
            factors.append(
                "recent demand trend is approximately stable"
            )

    if trend_class:
        factors.append(
            f"trend classification: {trend_class}"
        )

    if seasonal_factor is not None and not pd.isna(seasonal_factor):
        seasonal = safe_float(
            seasonal_factor,
            default=1.0,
        )

        if seasonal > 1.05:
            factors.append(
                f"seasonality increases expected demand "
                f"(factor {seasonal:.2f})"
            )

        elif seasonal < 0.95:
            factors.append(
                f"seasonality decreases expected demand "
                f"(factor {seasonal:.2f})"
            )

        else:
            factors.append(
                f"seasonal effect is close to neutral "
                f"(factor {seasonal:.2f})"
            )

    if seasonality_source:
        factors.append(
            f"seasonality source: {seasonality_source}"
        )

    return factors


def build_demand_correction_factors(
    stockout_correction: float = 0.0,
    excluded_outlier_qty: float = 0.0,
    structural_shift: bool = False,
) -> list[str]:
    """
    Explain corrections made before forecasting.
    """

    factors = []

    stockout_correction = safe_float(
        stockout_correction
    )

    excluded_outlier_qty = safe_float(
        excluded_outlier_qty
    )

    if stockout_correction > 0:
        factors.append(
            f"estimated lost demand from stockouts: "
            f"+{stockout_correction:.1f} units"
        )

    if excluded_outlier_qty > 0:
        factors.append(
            f"{excluded_outlier_qty:.1f} units of "
            f"potential one-off demand were excluded "
            f"from the regular-demand baseline"
        )

    if structural_shift:
        factors.append(
            "persistent demand increase was classified "
            "as a structural shift and kept in the baseline"
        )

    return factors


def build_inventory_factors(
    current_stock: float,
    goods_in_transit: float,
    stock_coverage_months: float | None = None,
    inventory_position_coverage_months: float | None = None,
) -> list[str]:
    """
    Explain inventory-related inputs.
    """

    factors = []

    current_stock = safe_float(current_stock)
    goods_in_transit = safe_float(goods_in_transit)

    factors.append(
        f"current stock: {current_stock:.1f} units"
    )

    if goods_in_transit > 0:
        factors.append(
            f"goods already in transit: "
            f"{goods_in_transit:.1f} units"
        )
    else:
        factors.append(
            "no goods in transit were included"
        )

    if (
        stock_coverage_months is not None
        and not pd.isna(stock_coverage_months)
    ):
        coverage = safe_float(
            stock_coverage_months
        )

        factors.append(
            f"current stock covers approximately "
            f"{coverage:.2f} months"
        )

    if (
        inventory_position_coverage_months is not None
        and not pd.isna(
            inventory_position_coverage_months
        )
    ):
        coverage = safe_float(
            inventory_position_coverage_months
        )

        factors.append(
            f"stock plus transit covers approximately "
            f"{coverage:.2f} months"
        )

    return factors


def build_recommendation_explanation(
    row: pd.Series | dict,
) -> dict:
    """
    Build complete explainable output for one SKU.

    This function combines:
    - forecast
    - safety stock
    - inventory
    - goods in transit
    - MOQ
    - seasonality
    - trend
    - stockout correction
    - excluded anomalies
    - structural shift
    - urgency
    - risk
    """

    if isinstance(row, dict):
        row = pd.Series(row)

    sku = str(row.get("sku", ""))

    monthly_forecast = safe_float(
        row.get("monthly_forecast", 0)
    )

    lead_time_demand = safe_float(
        row.get("lead_time_demand", 0)
    )

    safety_stock = safe_float(
        row.get("safety_stock", 0)
    )

    current_stock = safe_float(
        row.get("current_stock", 0)
    )

    goods_in_transit = safe_float(
        row.get("goods_in_transit", 0)
    )

    raw_recommended_qty = safe_float(
        row.get("raw_recommended_qty", 0)
    )

    recommended_qty = safe_float(
        row.get("recommended_qty", 0)
    )

    moq = safe_float(
        row.get("moq", 1),
        default=1.0,
    )

    urgency = str(
        row.get("urgency", "low")
    )

    risk = str(
        row.get("risk", "low")
    )

    formula_info = build_formula_explanation(
        lead_time_demand=lead_time_demand,
        safety_stock=safety_stock,
        current_stock=current_stock,
        goods_in_transit=goods_in_transit,
        raw_recommended_qty=raw_recommended_qty,
        recommended_qty=recommended_qty,
        moq=moq,
    )

    forecast_factors = build_forecast_factors(
        baseline_demand=row.get(
            "baseline_demand"
        ),
        growth_factor=row.get(
            "growth_factor"
        ),
        trend_class=row.get(
            "trend_class"
        ),
        seasonal_factor=row.get(
            "seasonal_factor"
        ),
        seasonality_source=row.get(
            "seasonality_source"
        ),
    )

    correction_factors = (
        build_demand_correction_factors(
            stockout_correction=row.get(
                "stockout_correction",
                0,
            ),
            excluded_outlier_qty=row.get(
                "excluded_outlier_qty",
                0,
            ),
            structural_shift=safe_bool(
                row.get(
                    "has_structural_shift",
                    False,
                )
            ),
        )
    )

    inventory_factors = build_inventory_factors(
        current_stock=current_stock,
        goods_in_transit=goods_in_transit,
        stock_coverage_months=row.get(
            "stock_coverage_months"
        ),
        inventory_position_coverage_months=row.get(
            "inventory_position_coverage_months"
        ),
    )

    if recommended_qty <= 0:
        summary = (
            f"SKU {sku}: no new order is currently required. "
            f"Available stock and goods in transit are sufficient "
            f"for the calculated demand."
        )
    else:
        summary = (
            f"SKU {sku}: recommend ordering "
            f"{recommended_qty:.0f} units. "
            f"Expected monthly demand is "
            f"{monthly_forecast:.1f} units, "
            f"with urgency '{urgency}' "
            f"and recommendation risk '{risk}'."
        )

    return {
        "summary": summary,

        "calculation": {
            "monthly_forecast": monthly_forecast,
            "lead_time_demand": lead_time_demand,
            "safety_stock": safety_stock,
            "current_stock": current_stock,
            "goods_in_transit": goods_in_transit,
            "raw_recommended_qty": raw_recommended_qty,
            "moq": moq,
            "recommended_qty": recommended_qty,
            "formula": formula_info["formula"],
        },

        "forecast_factors": forecast_factors,

        "demand_corrections": correction_factors,

        "inventory_factors": inventory_factors,

        "rounding_explanation": (
            formula_info[
                "rounding_explanation"
            ]
        ),

        "urgency": urgency,

        "risk": risk,
    }


def add_explanations(
    recommendations: pd.DataFrame,
) -> pd.DataFrame:
    """
    Add explanation payloads to all recommendation rows.
    """

    if recommendations.empty:
        result = recommendations.copy()

        result["explanation"] = pd.Series(
            dtype="object"
        )

        return result

    df = recommendations.copy()

    df["explanation"] = df.apply(
        build_recommendation_explanation,
        axis=1,
    )

    df["reason"] = df["explanation"].apply(
        lambda value: value["summary"]
    )

    return df
