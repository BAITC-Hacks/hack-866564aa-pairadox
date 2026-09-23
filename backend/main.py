from __future__ import annotations

import math
from io import BytesIO
from typing import Any

import numpy as np
import pandas as pd

from fastapi import (
    FastAPI,
    HTTPException,
    Query,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    StreamingResponse,
)

from .config import (
    SALES_HISTORY_FILE,
    MONTHLY_SALES_FILE,
    INVENTORY_FILE,
    MOQ_FILE,
    IN_TRANSIT_FILE,
    SEASONALITY_FILE,
    DEFAULT_LEAD_TIME_MONTHS,
    DEFAULT_SERVICE_LEVEL,
    DEFAULT_MONTHS_AHEAD,
    DEFAULT_ANOMALY_REPLACEMENT_STRATEGY,
    DEFAULT_APPLY_ANOMALY_EXCLUSION,
    DEFAULT_APPLY_STOCKOUT_CORRECTION,
    DEFAULT_APPLY_SEASONALITY,
    DEFAULT_APPLY_GROWTH_TREND,
)

from .services.preprocessing import (
    load_all_core_data,
)

from .services.pipeline import (
    run_procurement_pipeline
)

from .models.schemas import (
    RecommendationOut,
    HealthOut,
    ApiInfoOut,
)


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="Procurement Recommendation API",
    description=(
        "API for automatic supplier replenishment "
        "recommendations, anomaly detection, stockout "
        "correction, demand forecasting and "
        "counterfactual analysis."
    ),
    version="1.0.0",
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# APPLICATION CACHE
# ============================================================

DATA_CACHE: dict[str, Any] = {}

PIPELINE_CACHE: dict[str, Any] = {}

PIPELINE_ERROR: str | None = None


# ============================================================
# JSON HELPERS
# ============================================================

def json_safe_value(
    value: Any,
) -> Any:
    """
    Convert pandas/numpy values to JSON-safe Python values.

    Handles:
        NaN
        infinity
        numpy numbers
        numpy bool
        Timestamp
        NaT
    """

    if value is None:
        return None

    if isinstance(
        value,
        (
            pd.Timestamp,
            np.datetime64,
        ),
    ):
        if pd.isna(value):
            return None

        return pd.Timestamp(
            value
        ).isoformat()

    if isinstance(
        value,
        np.integer,
    ):
        return int(value)

    if isinstance(
        value,
        np.floating,
    ):
        value = float(value)

    if isinstance(
        value,
        np.bool_,
    ):
        return bool(value)

    if isinstance(
        value,
        float,
    ):
        if not math.isfinite(value):
            return None

        return value

    try:
        if pd.isna(value):
            return None
    except (
        TypeError,
        ValueError,
    ):
        pass

    return value


def dataframe_to_records(
    df: pd.DataFrame | None,
) -> list[dict[str, Any]]:
    """
    Convert DataFrame to JSON-safe list of dictionaries.
    """

    if df is None or df.empty:
        return []

    records = []

    for record in df.to_dict(
        orient="records"
    ):

        clean_record = {}

        for (
            key,
            value,
        ) in record.items():

            clean_record[key] = (
                json_safe_value(
                    value
                )
            )

        records.append(
            clean_record
        )

    return records


def normalize_requested_sku(
    sku: str,
) -> str:
    """
    Normalize SKU received from URL/request.
    """

    return (
        str(sku)
        .strip()
        .replace("_", "")
    )


# ============================================================
# LOAD DATA
# ============================================================

def load_project_data() -> dict:
    """
    Load all source Excel files.

    preprocessing.py converts supplier-specific Excel layouts
    into normalized DataFrames used by the analytical pipeline.
    """

    return load_all_core_data(
        sales_file=(
            SALES_HISTORY_FILE
        ),
        monthly_sales_file=(
            MONTHLY_SALES_FILE
        ),
        inventory_file=(
            INVENTORY_FILE
        ),
        moq_file=(
            MOQ_FILE
        ),
        in_transit_file=(
            IN_TRANSIT_FILE
        ),
        seasonality_file=(
            SEASONALITY_FILE
        ),
    )


# ============================================================
# RUN PIPELINE
# ============================================================

def calculate_pipeline(
    data: dict,
) -> dict:
    """
    Run the default/full procurement pipeline.
    """

    return run_procurement_pipeline(
        sales=data["sales"],
        inventory=data["inventory"],

        provided_seasonality=data.get(
            "provided_seasonality"
        ),

        in_transit=data.get(
            "in_transit"
        ),

        moq=data.get(
            "moq"
        ),

        lead_times=None,

        months_ahead=(
            DEFAULT_MONTHS_AHEAD
        ),

        service_level=(
            DEFAULT_SERVICE_LEVEL
        ),

        default_lead_time_months=(
            DEFAULT_LEAD_TIME_MONTHS
        ),

        apply_anomaly_exclusion=(
            DEFAULT_APPLY_ANOMALY_EXCLUSION
        ),

        apply_stockout_correction=(
            DEFAULT_APPLY_STOCKOUT_CORRECTION
        ),

        apply_seasonality=(
            DEFAULT_APPLY_SEASONALITY
        ),

        apply_growth_trend=(
            DEFAULT_APPLY_GROWTH_TREND
        ),

        anomaly_replacement_strategy=(
            DEFAULT_ANOMALY_REPLACEMENT_STRATEGY
        ),
    )


# ============================================================
# REFRESH CACHE
# ============================================================

def refresh_pipeline_cache() -> dict:
    """
    Reload Excel files and recalculate the complete pipeline.

    This function is the single place responsible for
    rebuilding application state.
    """

    global DATA_CACHE
    global PIPELINE_CACHE
    global PIPELINE_ERROR

    try:

        data = load_project_data()

        pipeline = calculate_pipeline(
            data
        )

        DATA_CACHE = data
        PIPELINE_CACHE = pipeline
        PIPELINE_ERROR = None

        return pipeline

    except Exception as error:

        DATA_CACHE = {}
        PIPELINE_CACHE = {}

        PIPELINE_ERROR = (
            f"{type(error).__name__}: "
            f"{error}"
        )

        raise


# ============================================================
# GET PIPELINE
# ============================================================

def get_pipeline() -> dict:
    """
    Return cached pipeline result.

    If cache is empty, calculate it lazily.
    """

    if PIPELINE_CACHE:
        return PIPELINE_CACHE

    try:
        return refresh_pipeline_cache()

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=(
                "Procurement pipeline could not "
                f"be calculated: {error}"
            ),
        ) from error


# ============================================================
# GET SOURCE DATA
# ============================================================

def get_project_data() -> dict:
    """
    Return cached normalized source data.

    Pipeline is loaded first if necessary.
    """

    if not DATA_CACHE:
        get_pipeline()

    return DATA_CACHE


# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
def startup_event() -> None:
    """
    Try to calculate pipeline when API starts.

    If an Excel/parser problem exists, the API itself still
    starts so /health can expose the error instead of Uvicorn
    crashing completely.
    """

    try:
        refresh_pipeline_cache()

    except Exception as error:

        # Error is already stored in PIPELINE_ERROR.
        print(
            "Pipeline startup error:",
            error,
        )


# ============================================================
# ROOT
# ============================================================

@app.get(
    "/",
    response_model=ApiInfoOut,
    tags=["System"],
)
def root():
    """
    Basic API information.
    """

    return {
        "message":
            "Procurement Recommendation API is running",

        "version":
            "1.0.0",

        "dataset":
            "IEK",
    }


# ============================================================
# HEALTH
# ============================================================

@app.get(
    "/health",
    tags=["System"],
)
def health():
    """
    API and pipeline health status.

    PIPELINE_ERROR is intentionally included while developing
    the project because it makes Excel/parser problems much
    easier to diagnose.
    """

    recommendations = (
        PIPELINE_CACHE.get(
            "recommendations"
        )
        if PIPELINE_CACHE
        else None
    )

    recommendation_count = 0

    if (
        recommendations is not None
        and isinstance(
            recommendations,
            pd.DataFrame,
        )
    ):
        recommendation_count = len(
            recommendations
        )

    if PIPELINE_ERROR is not None:

        return {
            "status": "error",
            "pipeline_loaded": False,
            "recommendation_count": 0,
            "error": PIPELINE_ERROR,
        }

    return {
        "status": "ok",
        "pipeline_loaded":
            bool(PIPELINE_CACHE),
        "recommendation_count":
            recommendation_count,
        "error": None,
    }


# ============================================================
# MANUAL REFRESH
# ============================================================

@app.post(
    "/refresh",
    tags=["System"],
)
def refresh():
    """
    Reload Excel files and recalculate recommendations.

    Useful during development when source files are replaced
    without restarting FastAPI.
    """

    try:

        result = refresh_pipeline_cache()

        recommendations = result.get(
            "recommendations",
            pd.DataFrame(),
        )

        return {
            "status": "ok",
            "recommendation_count":
                len(recommendations),
        }

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=(
                "Pipeline refresh failed: "
                f"{error}"
            ),
        ) from error


# ============================================================
# GET ALL RECOMMENDATIONS
# ============================================================

@app.get(
    "/recommendations",
    tags=["Recommendations"],
)
def get_recommendations(
    urgency: str | None = Query(
        default=None,
        description=(
            "Optional urgency filter: "
            "critical, high, medium or low"
        ),
    ),
    risk: str | None = Query(
        default=None,
        description=(
            "Optional risk filter: "
            "high, medium or low"
        ),
    ),
    only_requiring_order: bool = Query(
        default=False,
        description=(
            "Return only SKUs with recommended_qty > 0"
        ),
    ),
        limit: int = Query(
        default=50,
        ge=1,
        le=500,
        description="Maximum number of recommendations",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of recommendations to skip",
    ),
):
    """
    Return procurement recommendations.

    Optional filters allow the frontend to request only
    critical/high-risk SKUs or only SKUs requiring an order.
    """

    pipeline = get_pipeline()

    recommendations = (
        pipeline[
            "recommendations"
        ].copy()
    )

    # --------------------------------------------------------
    # Urgency filter
    # --------------------------------------------------------

    if urgency is not None:

        urgency = (
            urgency
            .strip()
            .lower()
        )

        allowed = {
            "critical",
            "high",
            "medium",
            "low",
        }

        if urgency not in allowed:

            raise HTTPException(
                status_code=400,
                detail=(
                    "urgency must be one of: "
                    "critical, high, medium, low"
                ),
            )

        recommendations = (
            recommendations[
                recommendations[
                    "urgency"
                ].astype(str).str.lower()
                == urgency
            ]
        )

    # --------------------------------------------------------
    # Risk filter
    # --------------------------------------------------------

    if risk is not None:

        risk = (
            risk
            .strip()
            .lower()
        )

        allowed = {
            "high",
            "medium",
            "low",
        }

        if risk not in allowed:

            raise HTTPException(
                status_code=400,
                detail=(
                    "risk must be one of: "
                    "high, medium, low"
                ),
            )

        recommendations = (
            recommendations[
                recommendations[
                    "risk"
                ].astype(str).str.lower()
                == risk
            ]
        )

    # --------------------------------------------------------
    # Only SKUs requiring order
    # --------------------------------------------------------

    if only_requiring_order:

        recommended_qty = (
            pd.to_numeric(
                recommendations[
                    "recommended_qty"
                ],
                errors="coerce",
            )
            .fillna(0.0)
        )

        recommendations = (
            recommendations[
                recommended_qty > 0
            ]
        )

    recommendations = recommendations.iloc[
        offset:offset + limit
    ]

    return dataframe_to_records(
        recommendations
    )

# ============================================================
# GET ONE SKU DETAIL
# ============================================================

@app.get(
    "/recommendations/{sku}",
    tags=["Recommendations"],
)
def get_recommendation_detail(
    sku: str,
):
    """
    Return detailed analytics for one SKU.

    Includes:
        recommendation
        forecasts
        anomalies
        anomaly corrections
        stockout analysis
        structural shifts
    """

    pipeline = get_pipeline()

    normalized_sku = normalize_requested_sku(
        sku
    )

    # ========================================================
    # RECOMMENDATION
    # ========================================================

    recommendations = (
        pipeline.get(
            "recommendations",
            pd.DataFrame(),
        )
        .copy()
    )

    if recommendations.empty:
        raise HTTPException(
            status_code=404,
            detail="No recommendations available",
        )

    recommendations["sku"] = (
        recommendations["sku"]
        .astype(str)
        .str.strip()
        .str.replace(
            "_",
            "",
            regex=False,
        )
    )

    recommendation_rows = (
        recommendations[
            recommendations["sku"]
            == normalized_sku
        ]
    )

    if recommendation_rows.empty:
        raise HTTPException(
            status_code=404,
            detail=(
                f"SKU '{normalized_sku}' "
                f"was not found"
            ),
        )

    recommendation = (
        dataframe_to_records(
            recommendation_rows.head(1)
        )[0]
    )

    # ========================================================
    # FORECASTS
    # ========================================================

    forecasts = (
        pipeline.get(
            "forecasts",
            pd.DataFrame(),
        )
        .copy()
    )

    if (
        not forecasts.empty
        and "sku" in forecasts.columns
    ):

        forecasts["sku"] = (
            forecasts["sku"]
            .astype(str)
            .str.strip()
            .str.replace(
                "_",
                "",
                regex=False,
            )
        )

        sku_forecasts = (
            forecasts[
                forecasts["sku"]
                == normalized_sku
            ]
        )

    else:

        sku_forecasts = pd.DataFrame()

    # ========================================================
    # ANOMALIES
    # ========================================================

    anomalies = (
        pipeline.get(
            "anomalies",
            pd.DataFrame(),
        )
        .copy()
    )

    if (
        not anomalies.empty
        and "sku" in anomalies.columns
    ):

        anomalies["sku"] = (
            anomalies["sku"]
            .astype(str)
            .str.strip()
            .str.replace(
                "_",
                "",
                regex=False,
            )
        )

        sku_anomalies = (
            anomalies[
                anomalies["sku"]
                == normalized_sku
            ]
        )

        # Do not send normal transactions to the detail card.
        if (
            "anomaly_class"
            in sku_anomalies.columns
        ):

            sku_anomalies = (
                sku_anomalies[
                    sku_anomalies[
                        "anomaly_class"
                    ]
                    != "normal"
                ]
            )

    else:

        sku_anomalies = pd.DataFrame()

    # ========================================================
    # ANOMALY CORRECTIONS
    # ========================================================

    corrections = (
        pipeline.get(
            "anomaly_corrections",
            pd.DataFrame(),
        )
        .copy()
    )

    if (
        not corrections.empty
        and "sku" in corrections.columns
    ):

        corrections["sku"] = (
            corrections["sku"]
            .astype(str)
            .str.strip()
            .str.replace(
                "_",
                "",
                regex=False,
            )
        )

        sku_corrections = (
            corrections[
                corrections["sku"]
                == normalized_sku
            ]
        )

    else:

        sku_corrections = pd.DataFrame()

    # ========================================================
    # STOCKOUT ANALYSIS
    # ========================================================

    stockout = (
        pipeline.get(
            "stockout_analysis",
            pd.DataFrame(),
        )
        .copy()
    )

    if (
        not stockout.empty
        and "sku" in stockout.columns
    ):

        stockout["sku"] = (
            stockout["sku"]
            .astype(str)
            .str.strip()
            .str.replace(
                "_",
                "",
                regex=False,
            )
        )

        sku_stockout = (
            stockout[
                stockout["sku"]
                == normalized_sku
            ]
        )

    else:

        sku_stockout = pd.DataFrame()

    # ========================================================
    # STRUCTURAL SHIFTS
    # ========================================================

    structural = (
        pipeline.get(
            "structural_shifts",
            pd.DataFrame(),
        )
        .copy()
    )

    if (
        not structural.empty
        and "sku" in structural.columns
    ):

        structural["sku"] = (
            structural["sku"]
            .astype(str)
            .str.strip()
            .str.replace(
                "_",
                "",
                regex=False,
            )
        )

        sku_structural = (
            structural[
                structural["sku"]
                == normalized_sku
            ]
        )

    else:

        sku_structural = pd.DataFrame()

    # ========================================================
    # RESPONSE
    # ========================================================

    return {
        "sku":
            normalized_sku,

        "recommendation":
            recommendation,

        "forecasts":
            dataframe_to_records(
                sku_forecasts
            ),

        "anomalies":
            dataframe_to_records(
                sku_anomalies
            ),

        "anomaly_corrections":
            dataframe_to_records(
                sku_corrections
            ),

        "stockout_periods":
            dataframe_to_records(
                sku_stockout
            ),

        "structural_shifts":
            dataframe_to_records(
                sku_structural
            ),
    }

# ============================================================
# GET ANOMALIES
# ============================================================

@app.get(
    "/anomalies",
    tags=["Analytics"],
)
def get_anomalies(
    anomaly_class: str | None = Query(
        default=None,
        description=(
            "Optional filter: "
            "normal, review or potential_one_off"
        ),
    ),
    sku: str | None = Query(
        default=None,
        description="Optional SKU filter",
    ),
    only_suspicious: bool = Query(
        default=False,
        description=(
            "If true, normal transactions are excluded"
        ),
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=500,
        description="Maximum number of anomalies to return",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of anomalies to skip",
    ),
):
    """
    Return transaction-level anomaly detection results.

    Available anomaly classes:

        normal
        review
        potential_one_off

    Filters:
        sku
        anomaly_class
        only_suspicious
    """

    pipeline = get_pipeline()

    anomalies = (
        pipeline.get(
            "anomalies",
            pd.DataFrame(),
        )
        .copy()
    )

    # --------------------------------------------------------
    # No anomaly data
    # --------------------------------------------------------

    if anomalies.empty:
        return []

    # --------------------------------------------------------
    # Normalize SKU column
    # --------------------------------------------------------

    if "sku" in anomalies.columns:

        anomalies["sku"] = (
            anomalies["sku"]
            .astype(str)
            .str.strip()
            .str.replace(
                "_",
                "",
                regex=False,
            )
        )

    # --------------------------------------------------------
    # SKU FILTER
    # --------------------------------------------------------

    if sku is not None:

        normalized_sku = (
            normalize_requested_sku(
                sku
            )
        )

        if "sku" not in anomalies.columns:

            raise HTTPException(
                status_code=500,
                detail=(
                    "Anomaly results do not "
                    "contain SKU column"
                ),
            )

        anomalies = (
            anomalies[
                anomalies["sku"]
                == normalized_sku
            ]
        )

    # --------------------------------------------------------
    # ANOMALY CLASS FILTER
    # --------------------------------------------------------

    if anomaly_class is not None:

        normalized_class = (
            anomaly_class
            .strip()
            .lower()
        )

        allowed_classes = {
            "normal",
            "review",
            "potential_one_off",
        }

        if (
            normalized_class
            not in allowed_classes
        ):

            raise HTTPException(
                status_code=400,
                detail=(
                    "anomaly_class must be one of: "
                    "normal, review, potential_one_off"
                ),
            )

        if (
            "anomaly_class"
            not in anomalies.columns
        ):

            raise HTTPException(
                status_code=500,
                detail=(
                    "Anomaly results do not contain "
                    "'anomaly_class'"
                ),
            )

        anomalies = (
            anomalies[
                anomalies[
                    "anomaly_class"
                ]
                .astype(str)
                .str.lower()
                == normalized_class
            ]
        )

    # --------------------------------------------------------
    # ONLY SUSPICIOUS TRANSACTIONS
    # --------------------------------------------------------

    if (
        only_suspicious
        and "anomaly_class"
        in anomalies.columns
    ):

        anomalies = (
            anomalies[
                anomalies[
                    "anomaly_class"
                ]
                .astype(str)
                .str.lower()
                != "normal"
            ]
        )

    # --------------------------------------------------------
    # FRONTEND-USEFUL COLUMNS
    # --------------------------------------------------------

    useful_columns = [
        "sku",
        "date",
        "week",
        "document_number",
        "product_name",
        "quantity",

        "sku_median_order",
        "sku_mean_order",
        "sku_std_order",

        "median_ratio",

        "document_total",
        "document_share",

        "iqr_lower",
        "iqr_upper",
        "iqr_outlier",

        "large_vs_median",
        "concentration_flag",

        "anomaly_signal_count",
        "anomaly_class",
        "anomaly_reason",
    ]

    available_columns = [
        column
        for column in useful_columns
        if column in anomalies.columns
    ]

    anomalies = anomalies[
        available_columns
    ].copy()

    # --------------------------------------------------------
    # Sort suspicious rows first
    # --------------------------------------------------------

    if "anomaly_class" in anomalies.columns:

        anomaly_order = {
            "potential_one_off": 0,
            "review": 1,
            "normal": 2,
        }

        anomalies[
            "_anomaly_order"
        ] = (
            anomalies[
                "anomaly_class"
            ]
            .map(anomaly_order)
            .fillna(99)
        )

        sort_columns = [
            "_anomaly_order",
        ]

        if "sku" in anomalies.columns:
            sort_columns.append(
                "sku"
            )

        if "date" in anomalies.columns:
            sort_columns.append(
                "date"
            )

        anomalies = (
            anomalies
            .sort_values(
                sort_columns
            )
            .drop(
                columns=[
                    "_anomaly_order",
                ]
            )
        )

    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------
    # --------------------------------------------------------
    # PAGINATION
    # --------------------------------------------------------

    anomalies = anomalies.iloc[
        offset:offset + limit
    ] 

    return dataframe_to_records(
        anomalies.reset_index(
            drop=True
        )
    )

# ============================================================
# GET STOCKOUT ANALYSIS
# ============================================================

@app.get(
    "/stockouts",
    tags=["Analytics"],
)
def get_stockouts(
    sku: str | None = Query(
        default=None,
        description="Optional SKU filter",
    ),
    only_risk: bool = Query(
        default=True,
        description=(
            "If true, return only periods "
            "with detected stockout risk"
        ),
    ),
):
    """
    Return monthly stockout analysis.

    The endpoint shows:

        actual demand
        reference demand
        inventory level
        stockout risk
        estimated lost demand
        corrected demand

    By default only stockout-risk periods are returned.
    """

    pipeline = get_pipeline()

    stockout = (
        pipeline.get(
            "stockout_analysis",
            pd.DataFrame(),
        )
        .copy()
    )

    # --------------------------------------------------------
    # No stockout data
    # --------------------------------------------------------

    if stockout.empty:
        return []

    # --------------------------------------------------------
    # Normalize SKU
    # --------------------------------------------------------

    if "sku" in stockout.columns:

        stockout["sku"] = (
            stockout["sku"]
            .astype(str)
            .str.strip()
            .str.replace(
                "_",
                "",
                regex=False,
            )
        )

    # --------------------------------------------------------
    # SKU FILTER
    # --------------------------------------------------------

    if sku is not None:

        normalized_sku = (
            normalize_requested_sku(
                sku
            )
        )

        if "sku" not in stockout.columns:

            raise HTTPException(
                status_code=500,
                detail=(
                    "Stockout analysis does not "
                    "contain SKU column"
                ),
            )

        stockout = (
            stockout[
                stockout["sku"]
                == normalized_sku
            ]
        )

    # --------------------------------------------------------
    # ONLY STOCKOUT-RISK PERIODS
    # --------------------------------------------------------

    if only_risk:

        if "stockout_risk" in stockout.columns:

            stockout = (
                stockout[
                    stockout[
                        "stockout_risk"
                    ]
                    .fillna(False)
                    .astype(bool)
                ]
            )

    # --------------------------------------------------------
    # FRONTEND-USEFUL COLUMNS
    # --------------------------------------------------------

    useful_columns = [
        "sku",
        "month",

        "actual_demand",
        "reference_demand",

        "stock",
        "stock_ratio",

        "low_stock",
        "demand_drop",

        "stockout_risk",
        "stockout_risk_level",
        "stockout_reason",

        "estimated_lost_demand",
        "corrected_demand",
    ]

    available_columns = [
        column
        for column in useful_columns
        if column in stockout.columns
    ]

    stockout = stockout[
        available_columns
    ].copy()

    # --------------------------------------------------------
    # SORT
    # --------------------------------------------------------

    sort_columns = []

    if "sku" in stockout.columns:
        sort_columns.append(
            "sku"
        )

    if "month" in stockout.columns:
        sort_columns.append(
            "month"
        )

    if sort_columns:

        stockout = (
            stockout.sort_values(
                sort_columns
            )
        )

    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    return dataframe_to_records(
        stockout.reset_index(
            drop=True
        )
    )

# ============================================================
# GET STRUCTURAL SHIFTS
# ============================================================

@app.get(
    "/structural-shifts",
    tags=["Analytics"],
)
def get_structural_shifts(
    sku: str | None = Query(
        default=None,
        description="Optional SKU filter",
    ),
    only_shifts: bool = Query(
        default=True,
        description=(
            "If true, return only periods that belong "
            "to a detected structural demand shift"
        ),
    ),
):
    """
    Return weekly structural-demand-shift analysis.

    Structural shift means that increased demand persists
    across several periods rather than being a single
    unusually large transaction.

    This information is also used to protect genuine demand
    growth from anomaly exclusion.
    """

    pipeline = get_pipeline()

    structural = (
        pipeline.get(
            "structural_shifts",
            pd.DataFrame(),
        )
        .copy()
    )

    # --------------------------------------------------------
    # No structural-shift data
    # --------------------------------------------------------

    if structural.empty:
        return []

    # --------------------------------------------------------
    # Normalize SKU
    # --------------------------------------------------------

    if "sku" in structural.columns:

        structural["sku"] = (
            structural["sku"]
            .astype(str)
            .str.strip()
            .str.replace(
                "_",
                "",
                regex=False,
            )
        )

    # --------------------------------------------------------
    # SKU FILTER
    # --------------------------------------------------------

    if sku is not None:

        normalized_sku = (
            normalize_requested_sku(
                sku
            )
        )

        if "sku" not in structural.columns:

            raise HTTPException(
                status_code=500,
                detail=(
                    "Structural-shift analysis does not "
                    "contain SKU column"
                ),
            )

        structural = (
            structural[
                structural["sku"]
                == normalized_sku
            ]
        )

    # --------------------------------------------------------
    # ONLY STRUCTURAL-SHIFT PERIODS
    # --------------------------------------------------------

    if only_shifts:

        if (
            "structural_shift_period"
            in structural.columns
        ):

            structural = (
                structural[
                    structural[
                        "structural_shift_period"
                    ]
                    .fillna(False)
                    .astype(bool)
                ]
            )

        elif (
            "structural_shift"
            in structural.columns
        ):

            structural = (
                structural[
                    structural[
                        "structural_shift"
                    ]
                    .fillna(False)
                    .astype(bool)
                ]
            )

    # --------------------------------------------------------
    # FRONTEND-USEFUL COLUMNS
    # --------------------------------------------------------

    useful_columns = [
        "sku",
        "week",

        "weekly_demand",
        "baseline",

        "demand_ratio",

        "elevated",
        "elevated_run",

        "structural_shift",
        "structural_shift_period",

        "shift_extra_demand",

        "demand_class",
        "shift_reason",
    ]

    available_columns = [
        column
        for column in useful_columns
        if column in structural.columns
    ]

    structural = structural[
        available_columns
    ].copy()

    # --------------------------------------------------------
    # SORT
    # --------------------------------------------------------

    sort_columns = []

    if "sku" in structural.columns:
        sort_columns.append(
            "sku"
        )

    if "week" in structural.columns:
        sort_columns.append(
            "week"
        )

    if sort_columns:

        structural = (
            structural.sort_values(
                sort_columns
            )
        )

    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    return dataframe_to_records(
        structural.reset_index(
            drop=True
        )
    )

# ============================================================
# GET FORECASTS
# ============================================================

@app.get(
    "/forecasts",
    tags=["Analytics"],
)
def get_forecasts(
    sku: str | None = Query(
        default=None,
        description="Optional SKU filter",
    ),
):
    """
    Return future monthly demand forecasts.

    For every SKU the endpoint can show:

        forecast month
        baseline demand
        growth factor
        trend class
        seasonal factor
        seasonality source
        final forecast
        demand variability
    """

    pipeline = get_pipeline()

    forecasts = (
        pipeline.get(
            "forecasts",
            pd.DataFrame(),
        )
        .copy()
    )

    # --------------------------------------------------------
    # No forecast data
    # --------------------------------------------------------

    if forecasts.empty:
        return []

    # --------------------------------------------------------
    # Normalize SKU
    # --------------------------------------------------------

    if "sku" in forecasts.columns:

        forecasts["sku"] = (
            forecasts["sku"]
            .astype(str)
            .str.strip()
            .str.replace(
                "_",
                "",
                regex=False,
            )
        )

    # --------------------------------------------------------
    # SKU FILTER
    # --------------------------------------------------------

    if sku is not None:

        normalized_sku = (
            normalize_requested_sku(
                sku
            )
        )

        if "sku" not in forecasts.columns:

            raise HTTPException(
                status_code=500,
                detail=(
                    "Forecast results do not "
                    "contain SKU column"
                ),
            )

        forecasts = (
            forecasts[
                forecasts["sku"]
                == normalized_sku
            ]
        )

    # --------------------------------------------------------
    # FRONTEND-USEFUL COLUMNS
    # --------------------------------------------------------

    useful_columns = [
        "sku",
        "forecast_month",

        "baseline_demand",

        "growth_factor",
        "trend_class",

        "seasonal_factor",
        "seasonality_source",

        "forecast",

        "demand_std",
        "coefficient_of_variation",

        "forecast_explanation",
    ]

    available_columns = [
        column
        for column in useful_columns
        if column in forecasts.columns
    ]

    forecasts = forecasts[
        available_columns
    ].copy()

    # --------------------------------------------------------
    # SORT
    # --------------------------------------------------------

    sort_columns = []

    if "sku" in forecasts.columns:
        sort_columns.append(
            "sku"
        )

    if "forecast_month" in forecasts.columns:
        sort_columns.append(
            "forecast_month"
        )

    if sort_columns:

        forecasts = (
            forecasts.sort_values(
                sort_columns
            )
        )

    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    return dataframe_to_records(
        forecasts.reset_index(
            drop=True
        )
    )
# ============================================================
# GET SUPPLIER SUMMARY
# ============================================================

@app.get(
    "/suppliers",
    tags=["Suppliers"],
)
def get_suppliers():
    """
    Return procurement summary grouped by supplier.

    Current version:
        all loaded products belong to IEK.

    Later this endpoint can support several datasets,
    for example:
        IEK
        Systeme Electric
    """

    pipeline = get_pipeline()

    recommendations = (
        pipeline.get(
            "recommendations",
            pd.DataFrame(),
        )
        .copy()
    )

    # --------------------------------------------------------
    # No recommendations
    # --------------------------------------------------------

    if recommendations.empty:
        return []

    # --------------------------------------------------------
    # Supplier
    # --------------------------------------------------------
    #
    # Current project loads data from:
    #
    #     data/IEK/
    #
    # Therefore all current SKUs belong to IEK.
    # --------------------------------------------------------

    recommendations[
        "supplier"
    ] = "IEK"

    # --------------------------------------------------------
    # Normalize recommended quantity
    # --------------------------------------------------------

    recommendations[
        "_recommended_qty"
    ] = (
        pd.to_numeric(
            recommendations[
                "recommended_qty"
            ],
            errors="coerce",
        )
        .fillna(0.0)
        .clip(lower=0.0)
    )

    recommendations[
        "_requires_order"
    ] = (
        recommendations[
            "_recommended_qty"
        ] > 0
    )

    # --------------------------------------------------------
    # Make sure urgency exists
    # --------------------------------------------------------

    if "urgency" not in recommendations.columns:

        recommendations[
            "urgency"
        ] = "low"

    recommendations[
        "urgency"
    ] = (
        recommendations[
            "urgency"
        ]
        .fillna("low")
        .astype(str)
        .str.lower()
    )

    # --------------------------------------------------------
    # Build supplier summaries
    # --------------------------------------------------------

    supplier_records = []

    for (
        supplier,
        group,
    ) in recommendations.groupby(
        "supplier"
    ):

        urgency = group[
            "urgency"
        ]

        supplier_records.append(
            {
                "supplier":
                    str(supplier),

                "sku_count":
                    int(
                        len(group)
                    ),

                "skus_requiring_order":
                    int(
                        group[
                            "_requires_order"
                        ].sum()
                    ),

                "total_recommended_qty":
                    float(
                        group[
                            "_recommended_qty"
                        ].sum()
                    ),

                "critical_count":
                    int(
                        (
                            urgency
                            == "critical"
                        ).sum()
                    ),

                "high_count":
                    int(
                        (
                            urgency
                            == "high"
                        ).sum()
                    ),

                "medium_count":
                    int(
                        (
                            urgency
                            == "medium"
                        ).sum()
                    ),

                "low_count":
                    int(
                        (
                            urgency
                            == "low"
                        ).sum()
                    ),
            }
        )

    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    return supplier_records

# ============================================================
# COUNTERFACTUAL ANALYSIS
# ============================================================

@app.post(
    "/counterfactual",
    tags=["Counterfactual"],
)
def run_counterfactual(
    sku: str | None = Query(
        default=None,
        description=(
            "Optional SKU filter. "
            "If omitted, all SKUs are returned."
        ),
    ),
    apply_anomaly_exclusion: bool = Query(
        default=True,
        description=(
            "Exclude genuine one-off anomalies "
            "from regular demand"
        ),
    ),
    apply_stockout_correction: bool = Query(
        default=True,
        description=(
            "Reconstruct estimated lost demand "
            "during stockout periods"
        ),
    ),
    apply_seasonality: bool = Query(
        default=True,
        description=(
            "Apply seasonal demand factors"
        ),
    ),
    apply_growth_trend: bool = Query(
        default=True,
        description=(
            "Apply recent demand growth trend"
        ),
    ),
):
    """
    Run a custom counterfactual procurement scenario.

    This endpoint allows individual analytical modules
    to be enabled or disabled.

    Example:

        anomaly exclusion = False
        stockout correction = True
        seasonality = True
        growth trend = False

    The result is compared with the default full model.
    """

    # --------------------------------------------------------
    # 1. Get normalized source data
    # --------------------------------------------------------

    data = get_project_data()

    normalized_sku = None

    if sku is not None:

        normalized_sku = (
            normalize_requested_sku(
                sku
            )
        )

    # --------------------------------------------------------
    # 2. Run custom pipeline
    # --------------------------------------------------------

    try:

        custom_result = (
            run_procurement_pipeline(
                sales=data["sales"],

                inventory=data[
                    "inventory"
                ],

                provided_seasonality=(
                    data.get(
                        "provided_seasonality"
                    )
                ),

                in_transit=(
                    data.get(
                        "in_transit"
                    )
                ),

                moq=(
                    data.get(
                        "moq"
                    )
                ),

                lead_times=None,

                months_ahead=(
                    DEFAULT_MONTHS_AHEAD
                ),

                service_level=(
                    DEFAULT_SERVICE_LEVEL
                ),

                default_lead_time_months=(
                    DEFAULT_LEAD_TIME_MONTHS
                ),

                apply_anomaly_exclusion=(
                    apply_anomaly_exclusion
                ),

                apply_stockout_correction=(
                    apply_stockout_correction
                ),

                apply_seasonality=(
                    apply_seasonality
                ),

                apply_growth_trend=(
                    apply_growth_trend
                ),

                anomaly_replacement_strategy=(
                    DEFAULT_ANOMALY_REPLACEMENT_STRATEGY
                ),
            )
        )

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=(
                "Counterfactual calculation "
                f"failed: {error}"
            ),
        ) from error

    # --------------------------------------------------------
    # 3. Get custom recommendations
    # --------------------------------------------------------

    custom_recommendations = (
        custom_result.get(
            "recommendations",
            pd.DataFrame(),
        )
        .copy()
    )

    # --------------------------------------------------------
    # 4. Get default/full recommendations
    # --------------------------------------------------------

    default_pipeline = (
        get_pipeline()
    )

    default_recommendations = (
        default_pipeline.get(
            "recommendations",
            pd.DataFrame(),
        )
        .copy()
    )

    # --------------------------------------------------------
    # 5. Normalize SKU columns
    # --------------------------------------------------------

    for dataframe in [
        custom_recommendations,
        default_recommendations,
    ]:

        if (
            not dataframe.empty
            and "sku"
            in dataframe.columns
        ):

            dataframe["sku"] = (
                dataframe["sku"]
                .astype(str)
                .str.strip()
                .str.replace(
                    "_",
                    "",
                    regex=False,
                )
            )

    # --------------------------------------------------------
    # 6. Optional SKU filter
    # --------------------------------------------------------

    if normalized_sku is not None:

        custom_recommendations = (
            custom_recommendations[
                custom_recommendations[
                    "sku"
                ]
                == normalized_sku
            ]
        )

        default_recommendations = (
            default_recommendations[
                default_recommendations[
                    "sku"
                ]
                == normalized_sku
            ]
        )

        if (
            custom_recommendations.empty
            and default_recommendations.empty
        ):

            raise HTTPException(
                status_code=404,
                detail=(
                    f"SKU '{normalized_sku}' "
                    "was not found"
                ),
            )

    # --------------------------------------------------------
    # 7. Prepare default model comparison
    # --------------------------------------------------------

    default_columns = [
        "sku",
        "monthly_forecast",
        "recommended_qty",
    ]

    available_default_columns = [
        column
        for column in default_columns
        if column
        in default_recommendations.columns
    ]

    default_compare = (
        default_recommendations[
            available_default_columns
        ]
        .copy()
    )

    default_compare = (
        default_compare.rename(
            columns={
                "monthly_forecast":
                    "default_monthly_forecast",

                "recommended_qty":
                    "default_recommended_qty",
            }
        )
    )

    # --------------------------------------------------------
    # 8. Prepare custom scenario
    # --------------------------------------------------------

    custom_columns = [
        "sku",
        "monthly_forecast",
        "recommended_qty",
        "current_stock",
        "goods_in_transit",
        "growth_factor",
        "seasonal_factor",
        "excluded_outlier_qty",
        "stockout_correction",
        "urgency",
        "risk",
    ]

    available_custom_columns = [
        column
        for column in custom_columns
        if column
        in custom_recommendations.columns
    ]

    custom_compare = (
        custom_recommendations[
            available_custom_columns
        ]
        .copy()
    )

    # --------------------------------------------------------
    # 9. Merge default + custom
    # --------------------------------------------------------

    comparison = (
        custom_compare.merge(
            default_compare,
            on="sku",
            how="left",
        )
    )

    # --------------------------------------------------------
    # 10. Calculate differences
    # --------------------------------------------------------

    if {
        "recommended_qty",
        "default_recommended_qty",
    }.issubset(
        comparison.columns
    ):

        comparison[
            "recommended_qty_difference"
        ] = (
            pd.to_numeric(
                comparison[
                    "recommended_qty"
                ],
                errors="coerce",
            )
            .fillna(0.0)
            -
            pd.to_numeric(
                comparison[
                    "default_recommended_qty"
                ],
                errors="coerce",
            )
            .fillna(0.0)
        )

    if {
        "monthly_forecast",
        "default_monthly_forecast",
    }.issubset(
        comparison.columns
    ):

        comparison[
            "forecast_difference"
        ] = (
            pd.to_numeric(
                comparison[
                    "monthly_forecast"
                ],
                errors="coerce",
            )
            .fillna(0.0)
            -
            pd.to_numeric(
                comparison[
                    "default_monthly_forecast"
                ],
                errors="coerce",
            )
            .fillna(0.0)
        )

    # --------------------------------------------------------
    # 11. Scenario configuration
    # --------------------------------------------------------

    scenario = {
        "apply_anomaly_exclusion":
            apply_anomaly_exclusion,

        "apply_stockout_correction":
            apply_stockout_correction,

        "apply_seasonality":
            apply_seasonality,

        "apply_growth_trend":
            apply_growth_trend,
    }

    # --------------------------------------------------------
    # 12. Response
    # --------------------------------------------------------

    return {
        "sku":
            normalized_sku,

        "scenario":
            scenario,

        "results":
            dataframe_to_records(
                comparison.reset_index(
                    drop=True
                )
            ),
    }

# ============================================================
# EXPORT RECOMMENDATIONS
# ============================================================

@app.get(
    "/export",
    tags=["Export"],
)
def export_recommendations(
    format: str = Query(
        default="xlsx",
        description=(
            "Export format: xlsx or csv"
        ),
    ),
    only_requiring_order: bool = Query(
        default=False,
        description=(
            "If true, export only SKUs "
            "with recommended_qty > 0"
        ),
    ),
):
    """
    Export procurement recommendations.

    Supported formats:
        xlsx
        csv
    """

    pipeline = get_pipeline()

    recommendations = (
        pipeline.get(
            "recommendations",
            pd.DataFrame(),
        )
        .copy()
    )

    # --------------------------------------------------------
    # No recommendations
    # --------------------------------------------------------

    if recommendations.empty:

        raise HTTPException(
            status_code=404,
            detail=(
                "No recommendations "
                "available for export"
            ),
        )

    # --------------------------------------------------------
    # Optional filter
    # --------------------------------------------------------

    if only_requiring_order:

        recommended_qty = (
            pd.to_numeric(
                recommendations[
                    "recommended_qty"
                ],
                errors="coerce",
            )
            .fillna(0.0)
        )

        recommendations = (
            recommendations[
                recommended_qty > 0
            ]
            .copy()
        )

    # --------------------------------------------------------
    # Normalize format
    # --------------------------------------------------------

    export_format = (
        str(format)
        .strip()
        .lower()
    )

    if export_format not in {
        "csv",
        "xlsx",
    }:

        raise HTTPException(
            status_code=400,
            detail=(
                "format must be "
                "'csv' or 'xlsx'"
            ),
        )

    # ========================================================
    # CSV EXPORT
    # ========================================================

    if export_format == "csv":

        csv_content = (
            recommendations.to_csv(
                index=False,
                encoding="utf-8-sig",
            )
        )

        csv_bytes = (
            csv_content.encode(
                "utf-8-sig"
            )
        )

        buffer = BytesIO(
            csv_bytes
        )

        headers = {
            "Content-Disposition":
                (
                    "attachment; "
                    "filename="
                    "procurement_recommendations.csv"
                )
        }

        return StreamingResponse(
            buffer,
            media_type=(
                "text/csv; "
                "charset=utf-8"
            ),
            headers=headers,
        )

    # ========================================================
    # XLSX EXPORT
    # ========================================================

    output = BytesIO()

    try:

        with pd.ExcelWriter(
            output,
            engine="openpyxl",
        ) as writer:

            # ------------------------------------------------
            # Sheet 1: Recommendations
            # ------------------------------------------------

            recommendations.to_excel(
                writer,
                sheet_name="Recommendations",
                index=False,
            )

            # ------------------------------------------------
            # Sheet 2: Forecasts
            # ------------------------------------------------

            forecasts = (
                pipeline.get(
                    "forecasts",
                    pd.DataFrame(),
                )
            )

            if (
                forecasts is not None
                and not forecasts.empty
            ):

                forecasts.to_excel(
                    writer,
                    sheet_name="Forecasts",
                    index=False,
                )

            # ------------------------------------------------
            # Sheet 3: Anomalies
            # ------------------------------------------------

            anomalies = (
                pipeline.get(
                    "anomalies",
                    pd.DataFrame(),
                )
            )

            if (
                anomalies is not None
                and not anomalies.empty
            ):

                anomalies.to_excel(
                    writer,
                    sheet_name="Anomalies",
                    index=False,
                )

            # ------------------------------------------------
            # Sheet 4: Anomaly corrections
            # ------------------------------------------------

            corrections = (
                pipeline.get(
                    "anomaly_corrections",
                    pd.DataFrame(),
                )
            )

            if (
                corrections is not None
                and not corrections.empty
            ):

                corrections.to_excel(
                    writer,
                    sheet_name="Anomaly Corrections",
                    index=False,
                )

            # ------------------------------------------------
            # Sheet 5: Stockouts
            # ------------------------------------------------

            stockout = (
                pipeline.get(
                    "stockout_analysis",
                    pd.DataFrame(),
                )
            )

            if (
                stockout is not None
                and not stockout.empty
            ):

                stockout.to_excel(
                    writer,
                    sheet_name="Stockouts",
                    index=False,
                )

            # ------------------------------------------------
            # Sheet 6: Structural shifts
            # ------------------------------------------------

            structural = (
                pipeline.get(
                    "structural_shifts",
                    pd.DataFrame(),
                )
            )

            if (
                structural is not None
                and not structural.empty
            ):

                structural.to_excel(
                    writer,
                    sheet_name="Structural Shifts",
                    index=False,
                )

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=(
                "Could not create XLSX export: "
                f"{error}"
            ),
        ) from error

    # --------------------------------------------------------
    # Move buffer cursor back to beginning
    # --------------------------------------------------------

    output.seek(0)

    headers = {
        "Content-Disposition":
            (
                "attachment; "
                "filename="
                "procurement_recommendations.xlsx"
            )
    }

    return StreamingResponse(
        output,
        media_type=(
            "application/"
            "vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        headers=headers,
    )





