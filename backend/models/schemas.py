from typing import Any

from pydantic import BaseModel, Field


# ============================================================
# RECOMMENDATION
# ============================================================

class RecommendationOut(BaseModel):
    """
    Final procurement recommendation for one SKU.
    """

    sku: str

    monthly_forecast: float
    lead_time_months: float
    lead_time_demand: float

    demand_std: float
    safety_stock: float

    current_stock: float
    goods_in_transit: float
    inventory_position: float

    raw_recommended_qty: float

    minimum_order_qty: float = 0.0
    order_multiple: float = 1.0

    recommended_qty: float

    stock_coverage_months: float | None = None

    inventory_position_coverage_months: (
        float | None
    ) = None

    urgency: str
    risk: str

    has_stockout_risk: bool = False
    has_structural_shift: bool = False

    baseline_demand: float = 0.0
    growth_factor: float = 1.0
    trend_class: str = "stable"

    seasonal_factor: float = 1.0
    seasonality_source: str = "neutral"

    stockout_correction: float = 0.0
    stockout_periods: int = 0

    excluded_outlier_qty: float = 0.0
    anomaly_count: int = 0

    extra_weekly_demand: float = 0.0

    coefficient_of_variation: float = 0.0
    service_level: float = 0.95

    reason: str | None = None

    explanation: dict[str, Any] | None = None


# ============================================================
# ANOMALY
# ============================================================

class AnomalyOut(BaseModel):
    """
    Transaction-level anomaly returned by /anomalies.
    """

    sku: str

    document_number: str | None = None

    quantity: float

    anomaly_class: str

    anomaly_reason: str | None = None

    iqr_outlier: bool = False
    large_vs_median: bool = False
    concentration_flag: bool = False

    median_ratio: float | None = None
    document_share: float | None = None


# ============================================================
# STOCKOUT PERIOD
# ============================================================

class StockoutPeriodOut(BaseModel):
    """
    Stockout-risk period for one SKU.
    """

    sku: str

    month: str

    actual_demand: float = 0.0

    reference_demand: float | None = None

    corrected_demand: float = 0.0

    estimated_lost_demand: float = 0.0

    stock: float | None = None

    stockout_risk: bool = False

    stockout_risk_level: str = "low"

    stockout_reason: str | None = None


# ============================================================
# STRUCTURAL SHIFT
# ============================================================

class StructuralShiftOut(BaseModel):
    """
    Weekly structural-demand-shift information.
    """

    sku: str

    week: str

    weekly_demand: float

    baseline: float | None = None

    demand_ratio: float | None = None

    elevated: bool = False

    elevated_run: int = 0

    structural_shift: bool = False

    structural_shift_period: bool = False

    shift_extra_demand: float = 0.0

    demand_class: str = "normal"

    shift_reason: str | None = None


# ============================================================
# FORECAST
# ============================================================

class ForecastOut(BaseModel):
    """
    Monthly forecast for one SKU.
    """

    sku: str

    forecast_month: str

    baseline_demand: float

    growth_factor: float

    trend_class: str

    seasonal_factor: float

    seasonality_source: str

    forecast: float

    demand_std: float = 0.0

    coefficient_of_variation: float = 0.0

    forecast_explanation: str | None = None


# ============================================================
# SKU DETAIL
# ============================================================

class SkuDetailOut(BaseModel):
    """
    Detailed analytics card for one SKU.

    Used by:
        GET /recommendations/{sku}
    """

    sku: str

    recommendation: RecommendationOut

    forecasts: list[ForecastOut] = Field(
        default_factory=list
    )

    anomalies: list[AnomalyOut] = Field(
        default_factory=list
    )

    stockout_periods: list[StockoutPeriodOut] = Field(
        default_factory=list
    )

    structural_shifts: list[StructuralShiftOut] = Field(
        default_factory=list
    )


# ============================================================
# COUNTERFACTUAL REQUEST
# ============================================================

class CounterfactualRequest(BaseModel):
    """
    Request body for POST /counterfactual.
    """

    sku: str | None = None

    apply_anomaly_exclusion: bool = True

    apply_stockout_correction: bool = True

    apply_seasonality: bool = True

    apply_growth_trend: bool = True


# ============================================================
# COUNTERFACTUAL RESULT
# ============================================================

class CounterfactualScenarioOut(BaseModel):
    """
    Result of one counterfactual scenario.
    """

    scenario: str

    sku: str

    monthly_forecast: float

    recommended_qty: float

    current_stock: float

    goods_in_transit: float

    growth_factor: float

    seasonal_factor: float

    excluded_outlier_qty: float

    stockout_correction: float

    urgency: str

    risk: str


class CounterfactualOut(BaseModel):
    """
    Counterfactual comparison response.
    """

    sku: str | None = None

    scenarios: list[
        CounterfactualScenarioOut
    ] = Field(
        default_factory=list
    )


# ============================================================
# SUPPLIER
# ============================================================

class SupplierSummaryOut(BaseModel):
    """
    Aggregated procurement information by supplier.
    """

    supplier: str

    sku_count: int

    skus_requiring_order: int

    total_recommended_qty: float

    critical_count: int = 0

    high_count: int = 0

    medium_count: int = 0

    low_count: int = 0


# ============================================================
# HEALTH
# ============================================================

class HealthOut(BaseModel):
    """
    API health response.
    """

    status: str

    pipeline_loaded: bool = False

    recommendation_count: int = 0


# ============================================================
# API INFORMATION
# ============================================================

class ApiInfoOut(BaseModel):
    """
    Root API information.
    """

    message: str

    version: str

    dataset: str