import numpy as np
import pandas as pd

from .anomaly_detection import detect_transaction_anomalies
from .structural_shift import (
    analyze_structural_shifts,
    get_structural_shift_summary,
)
from .stockout import (
    reconstruct_stockout_demand,
    get_stockout_summary,
)
from .seasonality import build_seasonality_model
from .forecasting import (
    forecast_next_months,
    get_forecast_summary,
)
from .replenishment import calculate_recommendation
from .explanations import add_explanations


# ============================================================
# BASIC HELPERS
# ============================================================

def safe_float(
    value,
    default: float = 0.0,
) -> float:
    """
    Convert a value to a finite float safely.

    None, NaN, infinity and invalid values are replaced
    with default.
    """

    if value is None:
        return float(default)

    try:
        if pd.isna(value):
            return float(default)
    except (TypeError, ValueError):
        return float(default)

    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(default)

    if not np.isfinite(number):
        return float(default)

    return number


def safe_bool(
    value,
    default: bool = False,
) -> bool:
    """
    Convert a value to boolean safely.
    """

    if value is None:
        return default

    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass

    if isinstance(value, str):
        return value.strip().lower() in {
            "true",
            "1",
            "yes",
            "y",
        }

    return bool(value)


def normalize_sku_column(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Normalize SKU format between all datasets.

    Example:
        030200874_ -> 030200874
    """

    result = df.copy()

    if "sku" not in result.columns:
        return result

    result["sku"] = (
        result["sku"]
        .astype(str)
        .str.strip()
        .str.replace("_", "", regex=False)
    )

    return result


# ============================================================
# INPUT VALIDATION
# ============================================================

def validate_pipeline_inputs(
    sales: pd.DataFrame,
    inventory: pd.DataFrame,
) -> None:
    """
    Validate mandatory pipeline inputs before calculations.
    """

    if sales is None:
        raise ValueError(
            "sales cannot be None"
        )

    if inventory is None:
        raise ValueError(
            "inventory cannot be None"
        )

    if sales.empty:
        raise ValueError(
            "sales dataset is empty"
        )

    if inventory.empty:
        raise ValueError(
            "inventory dataset is empty"
        )

    required_sales = {
        "sku",
        "date",
        "quantity",
        "week",
    }

    missing_sales = (
        required_sales
        - set(sales.columns)
    )

    if missing_sales:
        raise ValueError(
            "Sales data is missing columns: "
            + ", ".join(
                sorted(missing_sales)
            )
        )

    required_inventory = {
        "sku",
        "month",
        "stock",
    }

    missing_inventory = (
        required_inventory
        - set(inventory.columns)
    )

    if missing_inventory:
        raise ValueError(
            "Inventory data is missing columns: "
            + ", ".join(
                sorted(missing_inventory)
            )
        )


# ============================================================
# PREPARE SALES
# ============================================================

def prepare_pipeline_sales(
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """
    Prepare transaction sales for the pipeline.

    Important:
    reset_index() is intentional.

    anomaly_detection.py preserves dataframe indexes, so a
    stable RangeIndex allows us later to map detected anomalies
    back to the exact source transaction.
    """

    df = normalize_sku_column(
        sales
    ).reset_index(drop=True)

    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce",
    )

    df["week"] = pd.to_datetime(
        df["week"],
        errors="coerce",
    )

    df["quantity"] = pd.to_numeric(
        df["quantity"],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "sku",
            "date",
            "week",
            "quantity",
        ]
    ).copy()

    df = df[
        df["quantity"] > 0
    ].copy()

    # Important: after dropna/filter we reset again so anomaly
    # indexes and corrected-sales indexes remain identical.
    df = df.reset_index(drop=True)

    return df


# ============================================================
# PREPARE INVENTORY
# ============================================================

def prepare_pipeline_inventory(
    inventory: pd.DataFrame,
) -> pd.DataFrame:
    """
    Normalize inventory data before the pipeline.
    """

    df = normalize_sku_column(
        inventory
    )

    df["month"] = pd.to_datetime(
        df["month"],
        errors="coerce",
    )

    df["stock"] = pd.to_numeric(
        df["stock"],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "sku",
            "month",
        ]
    ).copy()

    df["stock"] = (
        df["stock"]
        .fillna(0.0)
    )

    return df.reset_index(drop=True)


# ============================================================
# CURRENT INVENTORY
# ============================================================

def get_latest_inventory(
    inventory: pd.DataFrame,
) -> pd.DataFrame:
    """
    Return the latest known inventory for every SKU.

    Input:
        sku
        month
        stock

    Output:
        sku
        current_stock
    """

    if inventory is None or inventory.empty:
        return pd.DataFrame(
            columns=[
                "sku",
                "current_stock",
            ]
        )

    required = {
        "sku",
        "month",
        "stock",
    }

    missing = (
        required
        - set(inventory.columns)
    )

    if missing:
        raise ValueError(
            "Inventory is missing columns: "
            + ", ".join(sorted(missing))
        )

    df = normalize_sku_column(
        inventory
    )

    df["month"] = pd.to_datetime(
        df["month"],
        errors="coerce",
    )

    df["stock"] = pd.to_numeric(
        df["stock"],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "sku",
            "month",
        ]
    ).copy()

    latest = (
        df.sort_values(
            [
                "sku",
                "month",
            ]
        )
        .groupby(
            "sku",
            as_index=False,
        )
        .tail(1)
        [
            [
                "sku",
                "stock",
            ]
        ]
        .rename(
            columns={
                "stock":
                    "current_stock",
            }
        )
        .reset_index(drop=True)
    )

    latest["current_stock"] = (
        pd.to_numeric(
            latest["current_stock"],
            errors="coerce",
        )
        .fillna(0.0)
        .clip(lower=0.0)
    )

    return latest


# ============================================================
# OPTIONAL SKU-LEVEL DATA
# ============================================================

def prepare_optional_sku_values(
    data: pd.DataFrame | None,
    value_column: str,
    output_column: str,
    default_value: float = 0.0,
    aggregation: str = "sum",
) -> pd.DataFrame:
    """
    Normalize optional SKU-level datasets.

    Used for:
        goods in transit
        MOQ / order multiple
        lead time

    aggregation:
        "sum"
            Use when several rows for the same SKU should
            be added together.

        "last"
            Use when one final value per SKU should be kept.
    """

    if data is None or data.empty:
        return pd.DataFrame(
            columns=[
                "sku",
                output_column,
            ]
        )

    df = normalize_sku_column(
        data
    )

    if "sku" not in df.columns:
        raise ValueError(
            "Optional SKU dataset must contain 'sku'"
        )

    if value_column not in df.columns:
        raise ValueError(
            f"Optional SKU dataset must contain "
            f"'{value_column}'"
        )

    result = df[
        [
            "sku",
            value_column,
        ]
    ].copy()

    result[value_column] = (
        pd.to_numeric(
            result[value_column],
            errors="coerce",
        )
        .fillna(default_value)
    )

    if aggregation == "sum":

        result = (
            result.groupby(
                "sku",
                as_index=False,
            )[value_column]
            .sum()
        )

    elif aggregation == "last":

        result = (
            result.drop_duplicates(
                subset=["sku"],
                keep="last",
            )
            .reset_index(drop=True)
        )

    else:
        raise ValueError(
            "aggregation must be "
            "'sum' or 'last'"
        )

    if value_column != output_column:
        result = result.rename(
            columns={
                value_column:
                    output_column,
            }
        )

    return result


# ============================================================
# PREPARE GOODS IN TRANSIT
# ============================================================

def prepare_in_transit(
    in_transit: pd.DataFrame | None,
) -> pd.DataFrame:
    """
    Prepare goods-in-transit data.

    Expected normalized input:
        sku
        goods_in_transit
    """

    return prepare_optional_sku_values(
        data=in_transit,
        value_column="goods_in_transit",
        output_column="goods_in_transit",
        default_value=0.0,
        aggregation="sum",
    )


# ============================================================
# PREPARE MOQ / ORDER MULTIPLE
# ============================================================

def prepare_moq(
    moq: pd.DataFrame | None,
) -> pd.DataFrame:
    """
    Prepare supplier order multiple.

    Expected normalized input:
        sku
        moq

    In the current project, 'moq' is treated as an order
    multiple for backward compatibility.
    """

    result = prepare_optional_sku_values(
        data=moq,
        value_column="moq",
        output_column="moq",
        default_value=1.0,
        aggregation="last",
    )

    if not result.empty:
        result["moq"] = (
            pd.to_numeric(
                result["moq"],
                errors="coerce",
            )
            .fillna(1.0)
            .clip(lower=1.0)
        )

    return result


# ============================================================
# PREPARE LEAD TIMES
# ============================================================

def prepare_lead_times(
    lead_times: pd.DataFrame | None,
    default_lead_time_months: float = 1.0,
) -> pd.DataFrame:
    """
    Prepare supplier lead times.

    Expected normalized input:
        sku
        lead_time_months

    If lead time data is unavailable, the recommendation stage
    will use default_lead_time_months.
    """

    result = prepare_optional_sku_values(
        data=lead_times,
        value_column="lead_time_months",
        output_column="lead_time_months",
        default_value=default_lead_time_months,
        aggregation="last",
    )

    if not result.empty:
        result["lead_time_months"] = (
            pd.to_numeric(
                result["lead_time_months"],
                errors="coerce",
            )
            .fillna(
                default_lead_time_months
            )
            .clip(lower=0.0)
        )

    return result

# ============================================================
# ANOMALY CORRECTION
# ============================================================

def apply_anomaly_correction(
    sales: pd.DataFrame,
    anomalies: pd.DataFrame,
    structural_weekly: pd.DataFrame,
    replacement_strategy: str = "median",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Correct genuine one-off transactions before stockout
    reconstruction and forecasting.

    A transaction is corrected only when:

        anomaly_class == "potential_one_off"

    AND

        its week is NOT part of a structural shift.

    This prevents a single unusually large order from
    artificially increasing the regular-demand forecast.

    At the same time, persistent demand growth is preserved.

    replacement_strategy:
        "median"
            Replace anomalous quantity with the typical
            median transaction quantity for the same SKU.

        "zero"
            Remove the anomalous transaction quantity
            completely.

    Returns:
        corrected_sales
        correction_details
    """

    if replacement_strategy not in {
        "median",
        "zero",
    }:
        raise ValueError(
            "replacement_strategy must be "
            "'median' or 'zero'"
        )

    corrected = normalize_sku_column(
        sales
    ).copy()

    corrected = corrected.reset_index(
        drop=True
    )

    required = {
        "sku",
        "quantity",
        "week",
    }

    missing = (
        required
        - set(corrected.columns)
    )

    if missing:
        raise ValueError(
            "Sales data is missing columns required "
            "for anomaly correction: "
            + ", ".join(
                sorted(missing)
            )
        )

    corrected["quantity"] = (
        pd.to_numeric(
            corrected["quantity"],
            errors="coerce",
        )
    )

    corrected["week"] = pd.to_datetime(
        corrected["week"],
        errors="coerce",
    )

    # Keep original quantity for audit/explanation.
    corrected["original_quantity"] = (
        corrected["quantity"]
    )

    corrected[
        "anomaly_corrected"
    ] = False

    corrected[
        "excluded_anomaly_qty"
    ] = 0.0

    # --------------------------------------------------------
    # No anomalies
    # --------------------------------------------------------

    if (
        anomalies is None
        or anomalies.empty
    ):

        correction_details = (
            pd.DataFrame(
                columns=[
                    "sku",
                    "week",
                    "original_quantity",
                    "corrected_quantity",
                    "excluded_anomaly_qty",
                    "anomaly_class",
                    "anomaly_reason",
                    "protected_by_structural_shift",
                    "anomaly_corrected",
                ]
            )
        )

        return (
            corrected,
            correction_details,
        )

    anomaly_df = normalize_sku_column(
        anomalies
    ).copy()

    # --------------------------------------------------------
    # Identify potential one-off anomalies
    # --------------------------------------------------------

    if "anomaly_class" in anomaly_df.columns:

        anomaly_df[
            "_potential_one_off"
        ] = (
            anomaly_df[
                "anomaly_class"
            ]
            .fillna("")
            .eq("potential_one_off")
        )

    elif (
        "potential_one_off"
        in anomaly_df.columns
    ):

        anomaly_df[
            "_potential_one_off"
        ] = (
            anomaly_df[
                "potential_one_off"
            ]
            .fillna(False)
            .astype(bool)
        )

    elif "is_anomaly" in anomaly_df.columns:

        anomaly_df[
            "_potential_one_off"
        ] = (
            anomaly_df[
                "is_anomaly"
            ]
            .fillna(False)
            .astype(bool)
        )

    else:

        anomaly_df[
            "_potential_one_off"
        ] = False

    # --------------------------------------------------------
    # Normalize anomaly week
    # --------------------------------------------------------

    if "week" in anomaly_df.columns:

        anomaly_df["week"] = (
            pd.to_datetime(
                anomaly_df["week"],
                errors="coerce",
            )
        )

    # --------------------------------------------------------
    # Build structural-shift lookup
    # --------------------------------------------------------

    structural_keys = set()

    if (
        structural_weekly is not None
        and not structural_weekly.empty
        and {
            "sku",
            "week",
            "structural_shift_period",
        }.issubset(
            structural_weekly.columns
        )
    ):

        structural_df = (
            normalize_sku_column(
                structural_weekly
            )
        )

        structural_df["week"] = (
            pd.to_datetime(
                structural_df["week"],
                errors="coerce",
            )
        )

        structural_rows = (
            structural_df[
                structural_df[
                    "structural_shift_period"
                ]
                .fillna(False)
                .astype(bool)
            ]
        )

        structural_keys = set(
            zip(
                structural_rows["sku"],
                structural_rows["week"],
            )
        )

    # --------------------------------------------------------
    # Protect anomalies that belong to structural shifts
    # --------------------------------------------------------

    def is_protected_by_shift(
        row: pd.Series,
    ) -> bool:

        sku = str(
            row.get(
                "sku",
                "",
            )
        )

        week = row.get(
            "week"
        )

        return (
            sku,
            week,
        ) in structural_keys

    anomaly_df[
        "protected_by_structural_shift"
    ] = anomaly_df.apply(
        is_protected_by_shift,
        axis=1,
    )

    # Correct only genuine one-off anomalies.
    anomaly_df[
        "should_correct"
    ] = (
        anomaly_df[
            "_potential_one_off"
        ]
        & ~anomaly_df[
            "protected_by_structural_shift"
        ]
    )

    # --------------------------------------------------------
    # Calculate normal transaction median by SKU
    # --------------------------------------------------------

    sku_medians = (
        corrected
        .groupby("sku")["quantity"]
        .median()
        .to_dict()
    )

    correction_records = []

    # --------------------------------------------------------
    # Apply correction
    # --------------------------------------------------------

    for (
        index,
        anomaly_row,
    ) in anomaly_df.iterrows():

        is_one_off = safe_bool(
            anomaly_row.get(
                "_potential_one_off",
                False,
            )
        )

        # We only need detailed correction records for
        # potential one-off transactions.
        if not is_one_off:
            continue

        # Because prepare_pipeline_sales() resets the index
        # before anomaly detection, the anomaly index points
        # to the same transaction in corrected sales.
        if index not in corrected.index:
            continue

        sku = str(
            corrected.at[
                index,
                "sku",
            ]
        )

        original_quantity = safe_float(
            corrected.at[
                index,
                "quantity",
            ]
        )

        protected = safe_bool(
            anomaly_row.get(
                "protected_by_structural_shift",
                False,
            )
        )

        should_correct = safe_bool(
            anomaly_row.get(
                "should_correct",
                False,
            )
        )

        corrected_quantity = (
            original_quantity
        )

        excluded_quantity = 0.0

        # ----------------------------------------------------
        # Genuine one-off
        # ----------------------------------------------------

        if should_correct:

            if (
                replacement_strategy
                == "zero"
            ):

                corrected_quantity = 0.0

            else:

                median_quantity = (
                    safe_float(
                        sku_medians.get(
                            sku,
                            0.0,
                        )
                    )
                )

                # Never increase a transaction during anomaly
                # correction.
                corrected_quantity = min(
                    original_quantity,
                    median_quantity,
                )

            excluded_quantity = max(
                0.0,
                original_quantity
                - corrected_quantity,
            )

            corrected.at[
                index,
                "quantity",
            ] = corrected_quantity

            corrected.at[
                index,
                "anomaly_corrected",
            ] = True

            corrected.at[
                index,
                "excluded_anomaly_qty",
            ] = excluded_quantity

        # ----------------------------------------------------
        # Audit record
        # ----------------------------------------------------

        correction_records.append(
            {
                "sku":
                    sku,

                "week":
                    anomaly_row.get(
                        "week"
                    ),

                "original_quantity":
                    original_quantity,

                "corrected_quantity":
                    corrected_quantity,

                "excluded_anomaly_qty":
                    excluded_quantity,

                "anomaly_class":
                    anomaly_row.get(
                        "anomaly_class",
                        "potential_one_off",
                    ),

                "anomaly_reason":
                    anomaly_row.get(
                        "anomaly_reason",
                        "",
                    ),

                "protected_by_structural_shift":
                    protected,

                "anomaly_corrected":
                    should_correct,
            }
        )

    correction_details = (
        pd.DataFrame(
            correction_records
        )
    )

    return (
        corrected,
        correction_details,
    )


# ============================================================
# ANOMALY SUMMARY
# ============================================================

def build_anomaly_summary(
    anomaly_results: pd.DataFrame,
    correction_details: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Aggregate transaction anomaly information to SKU level.

    anomaly_count:
        Number of transactions classified as
        potential_one_off.

    excluded_outlier_qty:
        Quantity ACTUALLY excluded from regular demand.

    Important:
        If an anomaly belongs to a structural shift,
        it is not included in excluded_outlier_qty.
    """

    if (
        anomaly_results is None
        or anomaly_results.empty
    ):

        return pd.DataFrame(
            columns=[
                "sku",
                "anomaly_count",
                "excluded_outlier_qty",
            ]
        )

    df = normalize_sku_column(
        anomaly_results
    )

    # --------------------------------------------------------
    # Identify potential one-offs
    # --------------------------------------------------------

    if "anomaly_class" in df.columns:

        anomaly_mask = (
            df["anomaly_class"]
            .fillna("")
            .eq("potential_one_off")
        )

    elif (
        "potential_one_off"
        in df.columns
    ):

        anomaly_mask = (
            df["potential_one_off"]
            .fillna(False)
            .astype(bool)
        )

    elif "is_anomaly" in df.columns:

        anomaly_mask = (
            df["is_anomaly"]
            .fillna(False)
            .astype(bool)
        )

    else:

        anomaly_mask = pd.Series(
            False,
            index=df.index,
        )

    df[
        "_pipeline_anomaly"
    ] = anomaly_mask

    # --------------------------------------------------------
    # Count detected anomalies
    # --------------------------------------------------------

    counts = (
        df.groupby(
            "sku",
            as_index=False,
        )
        .agg(
            anomaly_count=(
                "_pipeline_anomaly",
                "sum",
            )
        )
    )

    counts[
        "anomaly_count"
    ] = (
        counts["anomaly_count"]
        .fillna(0)
        .astype(int)
    )

    # --------------------------------------------------------
    # Calculate actually excluded quantity
    # --------------------------------------------------------

    if (
        correction_details is not None
        and not correction_details.empty
        and "excluded_anomaly_qty"
        in correction_details.columns
    ):

        corrections = (
            normalize_sku_column(
                correction_details
            )
        )

        corrections[
            "excluded_anomaly_qty"
        ] = (
            pd.to_numeric(
                corrections[
                    "excluded_anomaly_qty"
                ],
                errors="coerce",
            )
            .fillna(0.0)
            .clip(lower=0.0)
        )

        excluded = (
            corrections
            .groupby(
                "sku",
                as_index=False,
            )
            .agg(
                excluded_outlier_qty=(
                    "excluded_anomaly_qty",
                    "sum",
                )
            )
        )

        summary = counts.merge(
            excluded,
            on="sku",
            how="left",
        )

    else:

        summary = counts.copy()

        summary[
            "excluded_outlier_qty"
        ] = 0.0

    summary[
        "excluded_outlier_qty"
    ] = (
        summary[
            "excluded_outlier_qty"
        ]
        .fillna(0.0)
    )

    return summary


# ============================================================
# STOCKOUT COUNTERFACTUAL
# ============================================================

def disable_stockout_correction(
    stockout_results: pd.DataFrame,
) -> pd.DataFrame:
    """
    Disable stockout demand reconstruction.

    Normally:
        corrected_demand =
            actual_demand
            + estimated_lost_demand

    Counterfactual:
        corrected_demand =
            actual_demand

    Stockout diagnostic flags are kept so the frontend can
    still show what periods were considered risky.
    """

    if (
        stockout_results is None
        or stockout_results.empty
    ):
        return stockout_results.copy()

    df = stockout_results.copy()

    if "actual_demand" not in df.columns:
        return df

    df["actual_demand"] = (
        pd.to_numeric(
            df["actual_demand"],
            errors="coerce",
        )
        .fillna(0.0)
        .clip(lower=0.0)
    )

    df["corrected_demand"] = (
        df["actual_demand"]
    )

    if (
        "estimated_lost_demand"
        in df.columns
    ):
        df[
            "estimated_lost_demand"
        ] = 0.0

    return df


# ============================================================
# NEUTRAL SEASONALITY
# ============================================================

def build_neutral_seasonality_model() -> dict:
    """
    Create a neutral seasonality model.

    Every month receives:
        seasonal_factor = 1.0

    Used when:
        apply_seasonality=False
    """

    month_names = {
        1: "янв",
        2: "фев",
        3: "мар",
        4: "апр",
        5: "май",
        6: "июн",
        7: "июл",
        8: "авг",
        9: "сен",
        10: "окт",
        11: "ноя",
        12: "дек",
    }

    neutral_factors = pd.DataFrame(
        {
            "month_number":
                list(
                    range(
                        1,
                        13,
                    )
                ),

            "seasonal_factor":
                [1.0] * 12,

            "month_name": [
                month_names[
                    month_number
                ]
                for month_number
                in range(
                    1,
                    13,
                )
            ],

            "seasonality_source":
                ["disabled"] * 12,
        }
    )

    return {
        "monthly_demand":
            pd.DataFrame(),

        "sku_factors":
            pd.DataFrame(),

        "provided_factors":
            neutral_factors.copy(),

        "global_factors":
            neutral_factors.copy(),
    }


# ============================================================
# DISABLE GROWTH TREND
# ============================================================

def neutralize_forecast_growth(
    forecasts: pd.DataFrame,
) -> pd.DataFrame:
    """
    Remove growth-trend influence from already calculated
    forecasts.

    Normal forecast:
        baseline
        * growth_factor
        * seasonal_factor

    Counterfactual forecast:
        baseline
        * 1.0
        * seasonal_factor

    The output is also changed to:
        growth_factor = 1.0
        trend_class = "stable"
    """

    if (
        forecasts is None
        or forecasts.empty
    ):
        return forecasts.copy()

    df = forecasts.copy()

    required = {
        "baseline_demand",
        "seasonal_factor",
    }

    if not required.issubset(
        df.columns
    ):
        return df

    baseline = (
        pd.to_numeric(
            df["baseline_demand"],
            errors="coerce",
        )
        .fillna(0.0)
        .clip(lower=0.0)
    )

    seasonal = (
        pd.to_numeric(
            df["seasonal_factor"],
            errors="coerce",
        )
        .fillna(1.0)
        .clip(lower=0.0)
    )

    df["growth_factor"] = 1.0
    df["trend_class"] = "stable"

    df["forecast"] = (
        baseline
        * seasonal
    )

    if (
        "forecast_explanation"
        in df.columns
    ):

        df[
            "forecast_explanation"
        ] = (
            "growth trend disabled; "
            "growth factor fixed at 1.00"
        )

    return df

# ============================================================
# LATEST FORECAST DETAILS
# ============================================================

def build_latest_forecast_details(
    forecasts: pd.DataFrame,
) -> pd.DataFrame:
    """
    Keep forecast parameters from the first upcoming month
    for every SKU.

    Replenishment uses forecast_summary for calculations.

    These fields are mainly used for:
        - explanations
        - frontend
        - counterfactual comparison
    """

    if (
        forecasts is None
        or forecasts.empty
    ):
        return pd.DataFrame(
            columns=[
                "sku",
                "baseline_demand",
                "growth_factor",
                "trend_class",
                "seasonal_factor",
                "seasonality_source",
            ]
        )

    df = normalize_sku_column(
        forecasts
    )

    if "forecast_month" in df.columns:
        df["forecast_month"] = pd.to_datetime(
            df["forecast_month"],
            errors="coerce",
        )

        df = df.sort_values(
            [
                "sku",
                "forecast_month",
            ]
        )

    else:
        df = df.sort_values(
            ["sku"]
        )

    wanted_columns = [
        "sku",
        "baseline_demand",
        "growth_factor",
        "trend_class",
        "seasonal_factor",
        "seasonality_source",
    ]

    available_columns = [
        column
        for column in wanted_columns
        if column in df.columns
    ]

    if "sku" not in available_columns:
        return pd.DataFrame(
            columns=wanted_columns
        )

    result = (
        df.groupby(
            "sku",
            as_index=False,
        )
        .first()
    )

    result = result[
        available_columns
    ].copy()

    return result.reset_index(
        drop=True
    )


# ============================================================
# EMPTY STRUCTURAL SUMMARY
# ============================================================

def build_empty_structural_summary(
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build a neutral structural-shift summary.

    Normally structural-shift detection is always performed
    because it is required to distinguish:

        one-off anomaly

    from:

        persistent increase in demand.

    This helper exists for defensive fallback behaviour.
    """

    if (
        sales is None
        or sales.empty
        or "sku" not in sales.columns
    ):
        return pd.DataFrame(
            columns=[
                "sku",
                "has_structural_shift",
                "latest_shift_week",
                "latest_weekly_demand",
                "previous_baseline",
                "extra_weekly_demand",
            ]
        )

    skus = (
        normalize_sku_column(
            sales
        )["sku"]
        .dropna()
        .drop_duplicates()
        .tolist()
    )

    return pd.DataFrame(
        {
            "sku": skus,
            "has_structural_shift": [
                False
            ] * len(skus),
            "latest_shift_week": [
                None
            ] * len(skus),
            "latest_weekly_demand": [
                None
            ] * len(skus),
            "previous_baseline": [
                None
            ] * len(skus),
            "extra_weekly_demand": [
                0.0
            ] * len(skus),
        }
    )


# ============================================================
# EMPTY STOCKOUT SUMMARY
# ============================================================

def build_empty_stockout_summary(
    demand: pd.DataFrame,
) -> pd.DataFrame:
    """
    Create neutral stockout summary if no stockout analysis
    is available.
    """

    if (
        demand is None
        or demand.empty
        or "sku" not in demand.columns
    ):
        return pd.DataFrame(
            columns=[
                "sku",
                "stockout_periods",
                "total_estimated_lost_demand",
                "corrected_demand_total",
                "has_stockout_risk",
            ]
        )

    df = normalize_sku_column(
        demand
    )

    skus = (
        df["sku"]
        .dropna()
        .drop_duplicates()
        .tolist()
    )

    return pd.DataFrame(
        {
            "sku": skus,
            "stockout_periods": [
                0
            ] * len(skus),
            "total_estimated_lost_demand": [
                0.0
            ] * len(skus),
            "corrected_demand_total": [
                0.0
            ] * len(skus),
            "has_stockout_risk": [
                False
            ] * len(skus),
        }
    )


# ============================================================
# NORMALIZE FORECAST SUMMARY
# ============================================================

def normalize_forecast_summary(
    forecast_summary: pd.DataFrame,
) -> pd.DataFrame:
    """
    Validate and normalize the output from
    get_forecast_summary().

    Expected columns:
        sku
        total_forecast
        average_monthly_forecast
        demand_std
    """

    if (
        forecast_summary is None
        or forecast_summary.empty
    ):
        return pd.DataFrame(
            columns=[
                "sku",
                "total_forecast",
                "average_monthly_forecast",
                "demand_std",
            ]
        )

    df = normalize_sku_column(
        forecast_summary
    )

    required = {
        "sku",
        "average_monthly_forecast",
        "demand_std",
    }

    missing = (
        required
        - set(df.columns)
    )

    if missing:
        raise ValueError(
            "Forecast summary is missing columns: "
            + ", ".join(
                sorted(missing)
            )
        )

    numeric_columns = [
        "total_forecast",
        "average_monthly_forecast",
        "demand_std",
    ]

    for column in numeric_columns:

        if column not in df.columns:
            continue

        df[column] = (
            pd.to_numeric(
                df[column],
                errors="coerce",
            )
            .fillna(0.0)
            .clip(lower=0.0)
        )

    return df.reset_index(
        drop=True
    )


# ============================================================
# NORMALIZE STOCKOUT SUMMARY
# ============================================================

def normalize_stockout_summary(
    stockout_summary: pd.DataFrame,
) -> pd.DataFrame:
    """
    Normalize stockout summary before merging it into the
    final recommendation table.
    """

    if (
        stockout_summary is None
        or stockout_summary.empty
    ):
        return pd.DataFrame(
            columns=[
                "sku",
                "stockout_periods",
                "total_estimated_lost_demand",
                "corrected_demand_total",
                "has_stockout_risk",
            ]
        )

    df = normalize_sku_column(
        stockout_summary
    )

    numeric_defaults = {
        "stockout_periods": 0,
        "total_estimated_lost_demand": 0.0,
        "corrected_demand_total": 0.0,
    }

    for (
        column,
        default,
    ) in numeric_defaults.items():

        if column not in df.columns:
            df[column] = default

        df[column] = (
            pd.to_numeric(
                df[column],
                errors="coerce",
            )
            .fillna(default)
        )

    if "has_stockout_risk" not in df.columns:

        df["has_stockout_risk"] = (
            df["stockout_periods"] > 0
        )

    else:

        df["has_stockout_risk"] = (
            df["has_stockout_risk"]
            .fillna(False)
            .astype(bool)
        )

    return df


# ============================================================
# NORMALIZE STRUCTURAL SUMMARY
# ============================================================

def normalize_structural_summary(
    structural_summary: pd.DataFrame,
) -> pd.DataFrame:
    """
    Normalize structural-shift summary.
    """

    if (
        structural_summary is None
        or structural_summary.empty
    ):
        return pd.DataFrame(
            columns=[
                "sku",
                "has_structural_shift",
                "latest_shift_week",
                "latest_weekly_demand",
                "previous_baseline",
                "extra_weekly_demand",
            ]
        )

    df = normalize_sku_column(
        structural_summary
    )

    if "has_structural_shift" not in df.columns:
        df["has_structural_shift"] = False

    df["has_structural_shift"] = (
        df["has_structural_shift"]
        .fillna(False)
        .astype(bool)
    )

    numeric_defaults = {
        "latest_weekly_demand": 0.0,
        "previous_baseline": 0.0,
        "extra_weekly_demand": 0.0,
    }

    for (
        column,
        default,
    ) in numeric_defaults.items():

        if column not in df.columns:
            df[column] = default

        df[column] = (
            pd.to_numeric(
                df[column],
                errors="coerce",
            )
        )

    if "extra_weekly_demand" in df.columns:
        df["extra_weekly_demand"] = (
            df["extra_weekly_demand"]
            .fillna(0.0)
        )

    return df


# ============================================================
# NORMALIZE ANOMALY SUMMARY
# ============================================================

def normalize_anomaly_summary(
    anomaly_summary: pd.DataFrame,
) -> pd.DataFrame:
    """
    Normalize anomaly summary before final recommendation
    calculation.
    """

    if (
        anomaly_summary is None
        or anomaly_summary.empty
    ):
        return pd.DataFrame(
            columns=[
                "sku",
                "anomaly_count",
                "excluded_outlier_qty",
            ]
        )

    df = normalize_sku_column(
        anomaly_summary
    )

    if "anomaly_count" not in df.columns:
        df["anomaly_count"] = 0

    if "excluded_outlier_qty" not in df.columns:
        df["excluded_outlier_qty"] = 0.0

    df["anomaly_count"] = (
        pd.to_numeric(
            df["anomaly_count"],
            errors="coerce",
        )
        .fillna(0)
        .astype(int)
    )

    df["excluded_outlier_qty"] = (
        pd.to_numeric(
            df["excluded_outlier_qty"],
            errors="coerce",
        )
        .fillna(0.0)
        .clip(lower=0.0)
    )

    return df


# ============================================================
# PREPARE RECOMMENDATION BASE
# ============================================================

def prepare_recommendation_base(
    forecast_summary: pd.DataFrame,
    current_inventory: pd.DataFrame,
    stockout_summary: pd.DataFrame,
    structural_summary: pd.DataFrame,
    anomaly_summary: pd.DataFrame,
    forecast_details: pd.DataFrame,
    in_transit: pd.DataFrame | None = None,
    moq: pd.DataFrame | None = None,
    lead_times: pd.DataFrame | None = None,
    default_lead_time_months: float = 1.0,
) -> pd.DataFrame:
    """
    Merge all information required to calculate final
    procurement recommendations.

    Final base contains information about:

        forecast
        demand variability
        inventory
        goods in transit
        MOQ / order multiple
        lead time
        stockout correction
        anomalies
        structural shifts
        trend
        seasonality
    """

    forecast_summary = (
        normalize_forecast_summary(
            forecast_summary
        )
    )

    if forecast_summary.empty:
        return pd.DataFrame()

    base = forecast_summary.copy()

    # Rename forecast to the name expected by
    # calculate_recommendation().
    base = base.rename(
        columns={
            "average_monthly_forecast":
                "monthly_forecast",
        }
    )

    # --------------------------------------------------------
    # Inventory
    # --------------------------------------------------------

    if (
        current_inventory is not None
        and not current_inventory.empty
    ):

        inventory_df = (
            normalize_sku_column(
                current_inventory
            )
        )

        if (
            "current_stock"
            not in inventory_df.columns
        ):
            raise ValueError(
                "current_inventory must contain "
                "'current_stock'"
            )

        inventory_df = (
            inventory_df[
                [
                    "sku",
                    "current_stock",
                ]
            ]
            .drop_duplicates(
                subset=["sku"],
                keep="last",
            )
        )

        base = base.merge(
            inventory_df,
            on="sku",
            how="left",
        )

    # --------------------------------------------------------
    # Stockout summary
    # --------------------------------------------------------

    stockout_df = (
        normalize_stockout_summary(
            stockout_summary
        )
    )

    if not stockout_df.empty:

        base = base.merge(
            stockout_df,
            on="sku",
            how="left",
        )

    # --------------------------------------------------------
    # Structural shifts
    # --------------------------------------------------------

    structural_df = (
        normalize_structural_summary(
            structural_summary
        )
    )

    if not structural_df.empty:

        base = base.merge(
            structural_df,
            on="sku",
            how="left",
        )

    # --------------------------------------------------------
    # Anomalies
    # --------------------------------------------------------

    anomaly_df = (
        normalize_anomaly_summary(
            anomaly_summary
        )
    )

    if not anomaly_df.empty:

        base = base.merge(
            anomaly_df,
            on="sku",
            how="left",
        )

    # --------------------------------------------------------
    # Forecast details
    # --------------------------------------------------------

    if (
        forecast_details is not None
        and not forecast_details.empty
    ):

        details_df = (
            normalize_sku_column(
                forecast_details
            )
        )

        details_df = (
            details_df.drop_duplicates(
                subset=["sku"],
                keep="first",
            )
        )

        base = base.merge(
            details_df,
            on="sku",
            how="left",
        )

    # --------------------------------------------------------
    # Goods in transit
    # --------------------------------------------------------

    transit_df = prepare_in_transit(
        in_transit
    )

    if not transit_df.empty:

        base = base.merge(
            transit_df,
            on="sku",
            how="left",
        )

    # --------------------------------------------------------
    # MOQ / order multiple
    # --------------------------------------------------------

    moq_df = prepare_moq(
        moq
    )

    if not moq_df.empty:

        base = base.merge(
            moq_df,
            on="sku",
            how="left",
        )

    # --------------------------------------------------------
    # Lead times
    # --------------------------------------------------------

    lead_time_df = prepare_lead_times(
        lead_times=lead_times,
        default_lead_time_months=(
            default_lead_time_months
        ),
    )

    if not lead_time_df.empty:

        base = base.merge(
            lead_time_df,
            on="sku",
            how="left",
        )

    # --------------------------------------------------------
    # Defaults
    # --------------------------------------------------------

    defaults = {
        "current_stock": 0.0,
        "goods_in_transit": 0.0,
        "moq": 1.0,
        "minimum_order_qty": 0.0,
        "lead_time_months":
            default_lead_time_months,
        "demand_std": 0.0,
        "coefficient_of_variation": 0.0,
        "has_stockout_risk": False,
        "has_structural_shift": False,
        "total_estimated_lost_demand": 0.0,
        "excluded_outlier_qty": 0.0,
        "anomaly_count": 0,
        "baseline_demand": 0.0,
        "growth_factor": 1.0,
        "trend_class": "stable",
        "seasonal_factor": 1.0,
        "seasonality_source": "neutral",
    }

    for (
        column,
        default,
    ) in defaults.items():

        if column not in base.columns:

            base[column] = default

        else:

            base[column] = (
                base[column]
                .fillna(default)
            )

    # --------------------------------------------------------
    # Numeric normalization
    # --------------------------------------------------------

    numeric_columns = {
        "monthly_forecast": 0.0,
        "current_stock": 0.0,
        "goods_in_transit": 0.0,
        "moq": 1.0,
        "minimum_order_qty": 0.0,
        "lead_time_months":
            default_lead_time_months,
        "demand_std": 0.0,
        "coefficient_of_variation": 0.0,
        "total_estimated_lost_demand": 0.0,
        "excluded_outlier_qty": 0.0,
        "baseline_demand": 0.0,
        "growth_factor": 1.0,
        "seasonal_factor": 1.0,
    }

    for (
        column,
        default,
    ) in numeric_columns.items():

        base[column] = (
            pd.to_numeric(
                base[column],
                errors="coerce",
            )
            .fillna(default)
        )

    # Quantities cannot be negative.
    non_negative_columns = [
        "monthly_forecast",
        "current_stock",
        "goods_in_transit",
        "minimum_order_qty",
        "lead_time_months",
        "demand_std",
        "coefficient_of_variation",
        "total_estimated_lost_demand",
        "excluded_outlier_qty",
        "baseline_demand",
        "seasonal_factor",
    ]

    for column in non_negative_columns:

        base[column] = (
            base[column]
            .clip(lower=0.0)
        )

    # MOQ/order multiple must never be zero.
    base["moq"] = (
        base["moq"]
        .clip(lower=1.0)
    )

    base["has_stockout_risk"] = (
        base["has_stockout_risk"]
        .fillna(False)
        .astype(bool)
    )

    base["has_structural_shift"] = (
        base["has_structural_shift"]
        .fillna(False)
        .astype(bool)
    )

    base["anomaly_count"] = (
        pd.to_numeric(
            base["anomaly_count"],
            errors="coerce",
        )
        .fillna(0)
        .astype(int)
    )

    return base.reset_index(
        drop=True
    )
# ============================================================
# BUILD FINAL RECOMMENDATIONS
# ============================================================

def build_recommendations(
    forecast_summary: pd.DataFrame,
    current_inventory: pd.DataFrame,
    stockout_summary: pd.DataFrame,
    structural_summary: pd.DataFrame,
    anomaly_summary: pd.DataFrame,
    forecast_details: pd.DataFrame,
    in_transit: pd.DataFrame | None = None,
    moq: pd.DataFrame | None = None,
    lead_times: pd.DataFrame | None = None,
    service_level: float = 0.95,
    default_lead_time_months: float = 1.0,
) -> pd.DataFrame:
    """
    Build final procurement recommendation for every SKU.

    This function combines:

        forecast
        current inventory
        goods in transit
        MOQ / order multiple
        supplier lead time
        stockout information
        structural shifts
        anomalies
        seasonality
        growth trend

    Then calculate_recommendation() applies:

        lead_time_demand
        + safety_stock
        - current_stock
        - goods_in_transit

    followed by supplier constraints.
    """

    # --------------------------------------------------------
    # 1. Prepare merged recommendation base
    # --------------------------------------------------------

    base = prepare_recommendation_base(
        forecast_summary=forecast_summary,
        current_inventory=current_inventory,
        stockout_summary=stockout_summary,
        structural_summary=structural_summary,
        anomaly_summary=anomaly_summary,
        forecast_details=forecast_details,
        in_transit=in_transit,
        moq=moq,
        lead_times=lead_times,
        default_lead_time_months=(
            default_lead_time_months
        ),
    )

    if base.empty:
        return pd.DataFrame()

    recommendations = []

    # --------------------------------------------------------
    # 2. Calculate recommendation for every SKU
    # --------------------------------------------------------

    for _, row in base.iterrows():

        sku = str(
            row.get(
                "sku",
                "",
            )
        )

        monthly_forecast = safe_float(
            row.get(
                "monthly_forecast",
                0.0,
            )
        )

        demand_std = safe_float(
            row.get(
                "demand_std",
                0.0,
            )
        )

        current_stock = safe_float(
            row.get(
                "current_stock",
                0.0,
            )
        )

        goods_in_transit = safe_float(
            row.get(
                "goods_in_transit",
                0.0,
            )
        )

        minimum_order_qty = safe_float(
            row.get(
                "minimum_order_qty",
                0.0,
            )
        )

        order_multiple = max(
            1.0,
            safe_float(
                row.get(
                    "moq",
                    1.0,
                ),
                default=1.0,
            ),
        )

        lead_time_months = max(
            0.0,
            safe_float(
                row.get(
                    "lead_time_months",
                    default_lead_time_months,
                ),
                default=default_lead_time_months,
            ),
        )

        coefficient_of_variation = (
            safe_float(
                row.get(
                    "coefficient_of_variation",
                    0.0,
                )
            )
        )

        stockout_risk = safe_bool(
            row.get(
                "has_stockout_risk",
                False,
            )
        )

        structural_shift = safe_bool(
            row.get(
                "has_structural_shift",
                False,
            )
        )

        # ----------------------------------------------------
        # Core replenishment calculation
        # ----------------------------------------------------

        result = calculate_recommendation(
            sku=sku,
            monthly_forecast=monthly_forecast,
            demand_std=demand_std,
            current_stock=current_stock,
            goods_in_transit=goods_in_transit,
            minimum_order_qty=(
                minimum_order_qty
            ),
            order_multiple=order_multiple,
            lead_time_months=(
                lead_time_months
            ),
            service_level=service_level,
            coefficient_of_variation=(
                coefficient_of_variation
            ),
            stockout_risk=stockout_risk,
            structural_shift=(
                structural_shift
            ),
        )

        # ----------------------------------------------------
        # 3. Add forecast information for explanations
        # ----------------------------------------------------

        result["baseline_demand"] = (
            safe_float(
                row.get(
                    "baseline_demand",
                    0.0,
                )
            )
        )

        result["growth_factor"] = (
            safe_float(
                row.get(
                    "growth_factor",
                    1.0,
                ),
                default=1.0,
            )
        )

        result["trend_class"] = str(
            row.get(
                "trend_class",
                "stable",
            )
        )

        result["seasonal_factor"] = (
            safe_float(
                row.get(
                    "seasonal_factor",
                    1.0,
                ),
                default=1.0,
            )
        )

        result["seasonality_source"] = str(
            row.get(
                "seasonality_source",
                "neutral",
            )
        )

        # ----------------------------------------------------
        # 4. Add stockout correction information
        # ----------------------------------------------------

        result["stockout_correction"] = (
            safe_float(
                row.get(
                    "total_estimated_lost_demand",
                    0.0,
                )
            )
        )

        result["stockout_periods"] = int(
            safe_float(
                row.get(
                    "stockout_periods",
                    0,
                )
            )
        )

        # ----------------------------------------------------
        # 5. Add anomaly information
        # ----------------------------------------------------

        result["excluded_outlier_qty"] = (
            safe_float(
                row.get(
                    "excluded_outlier_qty",
                    0.0,
                )
            )
        )

        result["anomaly_count"] = int(
            safe_float(
                row.get(
                    "anomaly_count",
                    0,
                )
            )
        )

        # ----------------------------------------------------
        # 6. Add structural shift information
        # ----------------------------------------------------

        result["has_structural_shift"] = (
            structural_shift
        )

        latest_shift_week = row.get(
            "latest_shift_week"
        )

        if (
            latest_shift_week is None
            or pd.isna(latest_shift_week)
        ):
            result[
                "latest_shift_week"
            ] = None

        else:
            result[
                "latest_shift_week"
            ] = latest_shift_week

        result["extra_weekly_demand"] = (
            safe_float(
                row.get(
                    "extra_weekly_demand",
                    0.0,
                )
            )
        )

        # ----------------------------------------------------
        # 7. Keep additional useful fields
        # ----------------------------------------------------

        result[
            "coefficient_of_variation"
        ] = coefficient_of_variation

        result[
            "service_level"
        ] = safe_float(
            service_level,
            default=0.95,
        )

        # ----------------------------------------------------
        # 8. Save result
        # ----------------------------------------------------

        recommendations.append(
            result
        )

    # --------------------------------------------------------
    # 9. Convert to dataframe
    # --------------------------------------------------------

    result_df = pd.DataFrame(
        recommendations
    )

    if result_df.empty:
        return result_df

    # --------------------------------------------------------
    # 10. Add human-readable explanations
    # --------------------------------------------------------

    result_df = add_explanations(
        result_df
    )

    # --------------------------------------------------------
    # 11. Sort recommendations by urgency
    # --------------------------------------------------------

    urgency_order = {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
    }

    result_df[
        "_urgency_order"
    ] = (
        result_df["urgency"]
        .map(urgency_order)
        .fillna(99)
    )

    result_df = (
        result_df
        .sort_values(
            [
                "_urgency_order",
                "sku",
            ]
        )
        .drop(
            columns=[
                "_urgency_order",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    return result_df


# ============================================================
# COUNTERFACTUAL METADATA
# ============================================================

def build_counterfactual_metadata(
    apply_anomaly_exclusion: bool,
    apply_stockout_correction: bool,
    apply_seasonality: bool,
    apply_growth_trend: bool,
    anomaly_replacement_strategy: str,
) -> dict:
    """
    Describe which analytical modules were enabled.

    This is useful for the API and frontend when comparing
    counterfactual scenarios.
    """

    return {
        "apply_anomaly_exclusion":
            bool(
                apply_anomaly_exclusion
            ),

        "apply_stockout_correction":
            bool(
                apply_stockout_correction
            ),

        "apply_seasonality":
            bool(
                apply_seasonality
            ),

        "apply_growth_trend":
            bool(
                apply_growth_trend
            ),

        "anomaly_replacement_strategy":
            anomaly_replacement_strategy,
    }


# ============================================================
# PIPELINE RESULT VALIDATION
# ============================================================

def validate_pipeline_result(
    recommendations: pd.DataFrame,
) -> None:
    """
    Perform lightweight validation of the final result.

    This catches accidental negative recommendations or
    missing essential columns before the API receives them.
    """

    if recommendations is None:
        raise ValueError(
            "Pipeline produced None recommendations"
        )

    if recommendations.empty:
        return

    required = {
        "sku",
        "monthly_forecast",
        "current_stock",
        "recommended_qty",
        "urgency",
        "risk",
    }

    missing = (
        required
        - set(recommendations.columns)
    )

    if missing:
        raise ValueError(
            "Final recommendations are missing columns: "
            + ", ".join(
                sorted(missing)
            )
        )

    numeric_columns = [
        "monthly_forecast",
        "current_stock",
        "recommended_qty",
    ]

    for column in numeric_columns:

        values = pd.to_numeric(
            recommendations[column],
            errors="coerce",
        )

        if values.isna().any():
            raise ValueError(
                f"Final recommendation column "
                f"'{column}' contains invalid values"
            )

        if (values < 0).any():
            raise ValueError(
                f"Final recommendation column "
                f"'{column}' contains negative values"
            )


# ============================================================
# SAFE STOCKOUT SUMMARY
# ============================================================

def get_pipeline_stockout_summary(
    stockout: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build stockout summary with a safe fallback.
    """

    if stockout is None or stockout.empty:

        return pd.DataFrame(
            columns=[
                "sku",
                "stockout_periods",
                "total_estimated_lost_demand",
                "corrected_demand_total",
                "has_stockout_risk",
            ]
        )

    return get_stockout_summary(
        stockout
    )


# ============================================================
# SAFE STRUCTURAL SUMMARY
# ============================================================

def get_pipeline_structural_summary(
    structural: pd.DataFrame,
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build structural shift summary with a neutral fallback.
    """

    if structural is None or structural.empty:

        return build_empty_structural_summary(
            sales
        )

    return get_structural_shift_summary(
        structural
    )

# ============================================================
# MAIN PROCUREMENT PIPELINE
# ============================================================

def run_procurement_pipeline(
    sales: pd.DataFrame,
    inventory: pd.DataFrame,
    provided_seasonality: pd.DataFrame | None = None,
    in_transit: pd.DataFrame | None = None,
    moq: pd.DataFrame | None = None,
    lead_times: pd.DataFrame | None = None,
    months_ahead: int = 3,
    service_level: float = 0.95,
    default_lead_time_months: float = 1.0,
    apply_anomaly_exclusion: bool = True,
    apply_stockout_correction: bool = True,
    apply_seasonality: bool = True,
    apply_growth_trend: bool = True,
    anomaly_replacement_strategy: str = "median",
) -> dict:
    """
    Run the complete procurement analytics pipeline.

    Pipeline:

        raw sales
            |
            v
        anomaly detection
            |
            v
        structural shift detection
            |
            v
        genuine one-off anomaly correction
            |
            v
        stockout demand reconstruction
            |
            v
        seasonality
            |
            v
        forecasting
            |
            v
        replenishment recommendation


    Counterfactual switches
    -----------------------

    apply_anomaly_exclusion:
        True:
            genuine one-off anomalies are corrected before
            stockout reconstruction and forecasting.

        False:
            original sales quantities are preserved.


    apply_stockout_correction:
        True:
            estimated hidden demand caused by likely stockouts
            is added to corrected demand.

        False:
            forecasting uses observed actual demand only.


    apply_seasonality:
        True:
            use calculated/provided seasonality.

        False:
            seasonal_factor is fixed at 1.0.


    apply_growth_trend:
        True:
            use calculated recent demand growth factor.

        False:
            growth_factor is fixed at 1.0.


    anomaly_replacement_strategy:
        "median":
            replace one-off quantity with median transaction
            quantity for the same SKU.

        "zero":
            completely remove the one-off transaction from
            regular demand.


    Returns
    -------
    Dictionary containing:

        recommendations
        forecasts
        anomalies
        anomaly_corrections
        corrected_sales
        structural_shifts
        stockout_analysis
        seasonality
        summaries
        counterfactual
    """

    # ========================================================
    # 0. VALIDATION
    # ========================================================

    validate_pipeline_inputs(
        sales=sales,
        inventory=inventory,
    )

    if months_ahead < 1:
        raise ValueError(
            "months_ahead must be at least 1"
        )

    if default_lead_time_months < 0:
        raise ValueError(
            "default_lead_time_months "
            "cannot be negative"
        )

    if anomaly_replacement_strategy not in {
        "median",
        "zero",
    }:
        raise ValueError(
            "anomaly_replacement_strategy must be "
            "'median' or 'zero'"
        )

    # ========================================================
    # 1. PREPARE INPUT DATA
    # ========================================================

    prepared_sales = prepare_pipeline_sales(
        sales
    )

    prepared_inventory = (
        prepare_pipeline_inventory(
            inventory
        )
    )

    if prepared_sales.empty:
        raise ValueError(
            "No valid sales rows remain after preprocessing"
        )

    if prepared_inventory.empty:
        raise ValueError(
            "No valid inventory rows remain after preprocessing"
        )

    # ========================================================
    # 2. TRANSACTION ANOMALIES
    # ========================================================

    anomalies = (
        detect_transaction_anomalies(
            prepared_sales
        )
    )

    # ========================================================
    # 3. STRUCTURAL DEMAND SHIFTS
    # ========================================================
    #
    # IMPORTANT:
    #
    # Structural shifts must be calculated BEFORE anomaly
    # correction.
    #
    # Otherwise a persistent real increase could accidentally
    # be removed as an anomaly.
    # ========================================================

    structural = (
        analyze_structural_shifts(
            prepared_sales
        )
    )

    structural_summary = (
        get_pipeline_structural_summary(
            structural=structural,
            sales=prepared_sales,
        )
    )

    # ========================================================
    # 4. ANOMALY CORRECTION
    # ========================================================

    if apply_anomaly_exclusion:

        (
            corrected_sales,
            anomaly_corrections,
        ) = apply_anomaly_correction(
            sales=prepared_sales,
            anomalies=anomalies,
            structural_weekly=structural,
            replacement_strategy=(
                anomaly_replacement_strategy
            ),
        )

    else:

        # Keep original demand untouched.
        corrected_sales = (
            prepared_sales.copy()
        )

        corrected_sales[
            "original_quantity"
        ] = corrected_sales[
            "quantity"
        ]

        corrected_sales[
            "anomaly_corrected"
        ] = False

        corrected_sales[
            "excluded_anomaly_qty"
        ] = 0.0

        # We still return detected anomalies, but nothing was
        # excluded in this counterfactual mode.
        anomaly_corrections = pd.DataFrame(
            columns=[
                "sku",
                "week",
                "original_quantity",
                "corrected_quantity",
                "excluded_anomaly_qty",
                "anomaly_class",
                "anomaly_reason",
                "protected_by_structural_shift",
                "anomaly_corrected",
            ]
        )

    # ========================================================
    # 5. ANOMALY SUMMARY
    # ========================================================

    anomaly_summary = (
        build_anomaly_summary(
            anomaly_results=anomalies,
            correction_details=(
                anomaly_corrections
            ),
        )
    )

    # ========================================================
    # 6. STOCKOUT RECONSTRUCTION
    # ========================================================
    #
    # CRITICAL FIX:
    #
    # We now pass corrected_sales instead of original sales.
    #
    # Therefore a one-off order no longer inflates
    # actual_demand -> corrected_demand -> forecast.
    # ========================================================

    stockout = (
        reconstruct_stockout_demand(
            sales=corrected_sales,
            inventory=prepared_inventory,
        )
    )

    # ========================================================
    # 7. OPTIONAL STOCKOUT COUNTERFACTUAL
    # ========================================================

    if not apply_stockout_correction:

        stockout = (
            disable_stockout_correction(
                stockout
            )
        )

    stockout_summary = (
        get_pipeline_stockout_summary(
            stockout
        )
    )

    # ========================================================
    # 8. SEASONALITY
    # ========================================================

    if apply_seasonality:

        seasonality_model = (
            build_seasonality_model(
                demand=stockout,
                provided_seasonality=(
                    provided_seasonality
                ),
            )
        )

    else:

        seasonality_model = (
            build_neutral_seasonality_model()
        )

    # ========================================================
    # 9. FORECAST
    # ========================================================

    forecasts = (
        forecast_next_months(
            demand=stockout,
            seasonality_model=(
                seasonality_model
            ),
            months_ahead=months_ahead,
        )
    )

    # ========================================================
    # 10. OPTIONAL GROWTH-TREND COUNTERFACTUAL
    # ========================================================

    if not apply_growth_trend:

        forecasts = (
            neutralize_forecast_growth(
                forecasts
            )
        )

    # ========================================================
    # 11. FORECAST SUMMARY
    # ========================================================

    forecast_summary = (
        get_forecast_summary(
            forecasts
        )
    )

    forecast_summary = (
        normalize_forecast_summary(
            forecast_summary
        )
    )

    # ========================================================
    # 12. FORECAST DETAILS
    # ========================================================

    forecast_details = (
        build_latest_forecast_details(
            forecasts
        )
    )

    # ========================================================
    # 13. CURRENT INVENTORY
    # ========================================================

    current_inventory = (
        get_latest_inventory(
            prepared_inventory
        )
    )

    # ========================================================
    # 14. FINAL REPLENISHMENT RECOMMENDATIONS
    # ========================================================

    recommendations = (
        build_recommendations(
            forecast_summary=(
                forecast_summary
            ),
            current_inventory=(
                current_inventory
            ),
            stockout_summary=(
                stockout_summary
            ),
            structural_summary=(
                structural_summary
            ),
            anomaly_summary=(
                anomaly_summary
            ),
            forecast_details=(
                forecast_details
            ),
            in_transit=in_transit,
            moq=moq,
            lead_times=lead_times,
            service_level=(
                service_level
            ),
            default_lead_time_months=(
                default_lead_time_months
            ),
        )
    )

    # ========================================================
    # 15. VALIDATE FINAL RESULT
    # ========================================================

    validate_pipeline_result(
        recommendations
    )

    # ========================================================
    # 16. COUNTERFACTUAL METADATA
    # ========================================================

    counterfactual = (
        build_counterfactual_metadata(
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
                anomaly_replacement_strategy
            ),
        )
    )

    # ========================================================
    # 17. FINAL OUTPUT
    # ========================================================

    return {
        # ----------------------------------------------------
        # Main result
        # ----------------------------------------------------

        "recommendations":
            recommendations,

        # ----------------------------------------------------
        # Forecast information
        # ----------------------------------------------------

        "forecasts":
            forecasts,

        # ----------------------------------------------------
        # Anomaly information
        # ----------------------------------------------------

        "anomalies":
            anomalies,

        "anomaly_corrections":
            anomaly_corrections,

        # Sales after one-off correction.
        "corrected_sales":
            corrected_sales,

        # ----------------------------------------------------
        # Structural shift information
        # ----------------------------------------------------

        "structural_shifts":
            structural,

        # ----------------------------------------------------
        # Stockout information
        # ----------------------------------------------------

        "stockout_analysis":
            stockout,

        # ----------------------------------------------------
        # Seasonality model
        # ----------------------------------------------------

        "seasonality":
            seasonality_model,

        # ----------------------------------------------------
        # Counterfactual configuration
        # ----------------------------------------------------

        "counterfactual":
            counterfactual,

        # ----------------------------------------------------
        # Useful aggregated tables
        # ----------------------------------------------------

        "summaries": {

            "forecast":
                forecast_summary,

            "stockout":
                stockout_summary,

            "structural_shift":
                structural_summary,

            "anomalies":
                anomaly_summary,

            "current_inventory":
                current_inventory,

            "forecast_details":
                forecast_details,
        },
    }


# ============================================================
# COUNTERFACTUAL COMPARISON HELPER
# ============================================================

def compare_counterfactual_scenarios(
    sales: pd.DataFrame,
    inventory: pd.DataFrame,
    provided_seasonality: pd.DataFrame | None = None,
    in_transit: pd.DataFrame | None = None,
    moq: pd.DataFrame | None = None,
    lead_times: pd.DataFrame | None = None,
    months_ahead: int = 3,
    service_level: float = 0.95,
    default_lead_time_months: float = 1.0,
    sku: str | None = None,
) -> pd.DataFrame:
    """
    Compare the full recommendation against several
    counterfactual scenarios.

    This helper is useful later for:

        POST /counterfactual

    Scenarios:

        full_model
        no_anomaly_exclusion
        no_stockout_correction
        no_seasonality
        no_growth_trend
    """

    scenarios = {
        "full_model": {
            "apply_anomaly_exclusion": True,
            "apply_stockout_correction": True,
            "apply_seasonality": True,
            "apply_growth_trend": True,
        },

        "no_anomaly_exclusion": {
            "apply_anomaly_exclusion": False,
            "apply_stockout_correction": True,
            "apply_seasonality": True,
            "apply_growth_trend": True,
        },

        "no_stockout_correction": {
            "apply_anomaly_exclusion": True,
            "apply_stockout_correction": False,
            "apply_seasonality": True,
            "apply_growth_trend": True,
        },

        "no_seasonality": {
            "apply_anomaly_exclusion": True,
            "apply_stockout_correction": True,
            "apply_seasonality": False,
            "apply_growth_trend": True,
        },

        "no_growth_trend": {
            "apply_anomaly_exclusion": True,
            "apply_stockout_correction": True,
            "apply_seasonality": True,
            "apply_growth_trend": False,
        },
    }

    records = []

    for (
        scenario_name,
        flags,
    ) in scenarios.items():

        result = run_procurement_pipeline(
            sales=sales,
            inventory=inventory,
            provided_seasonality=(
                provided_seasonality
            ),
            in_transit=in_transit,
            moq=moq,
            lead_times=lead_times,
            months_ahead=months_ahead,
            service_level=service_level,
            default_lead_time_months=(
                default_lead_time_months
            ),
            apply_anomaly_exclusion=(
                flags[
                    "apply_anomaly_exclusion"
                ]
            ),
            apply_stockout_correction=(
                flags[
                    "apply_stockout_correction"
                ]
            ),
            apply_seasonality=(
                flags[
                    "apply_seasonality"
                ]
            ),
            apply_growth_trend=(
                flags[
                    "apply_growth_trend"
                ]
            ),
        )

        recommendations = (
            result[
                "recommendations"
            ].copy()
        )

        if sku is not None:

            normalized_sku = (
                str(sku)
                .strip()
                .replace("_", "")
            )

            recommendations = (
                recommendations[
                    recommendations["sku"]
                    == normalized_sku
                ]
            )

        for _, row in (
            recommendations.iterrows()
        ):

            records.append(
                {
                    "scenario":
                        scenario_name,

                    "sku":
                        row.get(
                            "sku"
                        ),

                    "monthly_forecast":
                        safe_float(
                            row.get(
                                "monthly_forecast",
                                0.0,
                            )
                        ),

                    "recommended_qty":
                        safe_float(
                            row.get(
                                "recommended_qty",
                                0.0,
                            )
                        ),

                    "current_stock":
                        safe_float(
                            row.get(
                                "current_stock",
                                0.0,
                            )
                        ),

                    "goods_in_transit":
                        safe_float(
                            row.get(
                                "goods_in_transit",
                                0.0,
                            )
                        ),

                    "growth_factor":
                        safe_float(
                            row.get(
                                "growth_factor",
                                1.0,
                            ),
                            default=1.0,
                        ),

                    "seasonal_factor":
                        safe_float(
                            row.get(
                                "seasonal_factor",
                                1.0,
                            ),
                            default=1.0,
                        ),

                    "excluded_outlier_qty":
                        safe_float(
                            row.get(
                                "excluded_outlier_qty",
                                0.0,
                            )
                        ),

                    "stockout_correction":
                        safe_float(
                            row.get(
                                "stockout_correction",
                                0.0,
                            )
                        ),

                    "urgency":
                        row.get(
                            "urgency",
                            "low",
                        ),

                    "risk":
                        row.get(
                            "risk",
                            "low",
                        ),
                }
            )

    comparison = pd.DataFrame(
        records
    )

    if comparison.empty:
        return comparison

    scenario_order = {
        "full_model": 0,
        "no_anomaly_exclusion": 1,
        "no_stockout_correction": 2,
        "no_seasonality": 3,
        "no_growth_trend": 4,
    }

    comparison[
        "_scenario_order"
    ] = (
        comparison["scenario"]
        .map(scenario_order)
        .fillna(99)
    )

    comparison = (
        comparison
        .sort_values(
            [
                "sku",
                "_scenario_order",
            ]
        )
        .drop(
            columns=[
                "_scenario_order",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    return comparison