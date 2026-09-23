import numpy as np
import pandas as pd

from .seasonality import (
    get_seasonal_factor,
    apply_seasonality,
    build_seasonality_explanation,
)


def prepare_forecast_history(
    demand: pd.DataFrame,
) -> pd.DataFrame:
    """
    Prepare monthly demand history for forecasting.

    Preferred input:
        sku
        month
        corrected_demand

    Alternative:
        sku
        month
        demand
    """

    df = demand.copy()

    required_base = {
        "sku",
        "month",
    }

    missing = required_base - set(df.columns)

    if missing:
        raise ValueError(
            "Missing forecast history columns: "
            + ", ".join(sorted(missing))
        )

    if "corrected_demand" in df.columns:
        demand_column = "corrected_demand"

    elif "demand" in df.columns:
        demand_column = "demand"

    else:
        raise ValueError(
            "Forecast history must contain "
            "'corrected_demand' or 'demand'"
        )

    df["month"] = pd.to_datetime(
        df["month"],
        errors="coerce",
    )

    df["forecast_demand"] = pd.to_numeric(
        df[demand_column],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "sku",
            "month",
            "forecast_demand",
        ]
    ).copy()

    # Demand cannot be negative.
    df["forecast_demand"] = (
        df["forecast_demand"]
        .clip(lower=0)
    )

    df = (
        df.groupby(
            ["sku", "month"],
            as_index=False,
        )["forecast_demand"]
        .sum()
    )

    return df.sort_values(
        ["sku", "month"]
    ).reset_index(drop=True)


def calculate_baseline(
    history: pd.DataFrame,
    window: int = 3,
) -> pd.DataFrame:
    """
    Calculate recent baseline demand for every SKU.

    Median is used because it is more resistant to
    one unusually large period than mean.
    """

    if window < 2:
        raise ValueError(
            "baseline window must be at least 2"
        )

    results = []

    for sku, group in history.groupby("sku"):

        group = group.sort_values("month")

        recent = (
            group["forecast_demand"]
            .tail(window)
        )

        if recent.empty:
            continue

        baseline = recent.median()

        results.append(
            {
                "sku": sku,
                "baseline_demand": float(baseline),
                "baseline_months": int(len(recent)),
            }
        )

    return pd.DataFrame(results)


def calculate_linear_trend(
    values: pd.Series,
) -> float:
    """
    Calculate slope of demand history using linear regression.

    Positive slope -> demand growing.
    Negative slope -> demand falling.
    """

    clean = pd.to_numeric(
        values,
        errors="coerce",
    ).dropna()

    if len(clean) < 3:
        return 0.0

    y = clean.to_numpy(
        dtype=float
    )

    x = np.arange(
        len(y),
        dtype=float,
    )

    slope = np.polyfit(
        x,
        y,
        1,
    )[0]

    return float(slope)


def calculate_growth_factor(
    history: pd.DataFrame,
    trend_window: int = 6,
    minimum_factor: float = 0.70,
    maximum_factor: float = 1.50,
) -> pd.DataFrame:
    """
    Estimate growth factor from recent demand trend.

    The factor is capped so a noisy trend cannot produce
    an unrealistic forecast.

    Examples:
        1.10 -> approximately +10%
        0.90 -> approximately -10%
    """

    if trend_window < 3:
        raise ValueError(
            "trend_window must be at least 3"
        )

    results = []

    for sku, group in history.groupby("sku"):

        group = group.sort_values("month")

        recent = group.tail(
            trend_window
        )

        values = recent[
            "forecast_demand"
        ]

        slope = calculate_linear_trend(
            values
        )

        average = values.mean()

        if (
            pd.isna(average)
            or average <= 0
        ):
            growth_factor = 1.0

        else:

            relative_change = (
                slope / average
            )

            growth_factor = (
                1.0
                + relative_change
            )

        growth_factor = float(
            np.clip(
                growth_factor,
                minimum_factor,
                maximum_factor,
            )
        )

        results.append(
            {
                "sku": sku,
                "trend_slope": float(slope),
                "growth_factor": growth_factor,
                "trend_months": int(len(recent)),
            }
        )

    return pd.DataFrame(results)


def calculate_demand_variability(
    history: pd.DataFrame,
    window: int = 6,
) -> pd.DataFrame:
    """
    Calculate recent demand variability.

    Used later by safety-stock calculation.
    """

    results = []

    for sku, group in history.groupby("sku"):

        group = group.sort_values("month")

        recent = (
            group["forecast_demand"]
            .tail(window)
        )

        if len(recent) < 2:

            std = 0.0

        else:

            std = recent.std(
                ddof=1
            )

        mean = recent.mean()

        if (
            pd.isna(mean)
            or mean <= 0
        ):
            cv = 0.0

        else:
            cv = std / mean

        results.append(
            {
                "sku": sku,
                "demand_std": float(
                    0 if pd.isna(std) else std
                ),
                "coefficient_of_variation":
                    float(
                        0 if pd.isna(cv) else cv
                    ),
            }
        )

    return pd.DataFrame(results)


def classify_trend(
    growth_factor: float,
) -> str:
    """
    Human-readable trend classification.
    """

    if growth_factor >= 1.10:
        return "growing"

    if growth_factor <= 0.90:
        return "declining"

    return "stable"


def build_forecast_explanation(
    baseline: float,
    growth_factor: float,
    seasonal_factor: float,
    forecast: float,
    trend_class: str,
    seasonality_explanation: str,
) -> str:
    """
    Generate explainable forecast text.
    """

    return (
        f"baseline demand {baseline:.1f}; "
        f"trend={trend_class}; "
        f"growth factor {growth_factor:.2f}; "
        f"{seasonality_explanation}; "
        f"forecast {forecast:.1f}"
    )


def forecast_single_sku(
    sku: str,
    target_month: pd.Timestamp,
    baseline: float,
    growth_factor: float,
    seasonality_model: dict,
) -> dict:
    """
    Forecast one SKU for one future month.
    """

    month_number = (
        target_month.month
    )

    seasonality = (
        get_seasonal_factor(
            sku=sku,
            month_number=month_number,
            seasonality_model=seasonality_model,
        )
    )

    seasonal_factor = (
        seasonality[
            "seasonal_factor"
        ]
    )

    seasonality_source = (
        seasonality["source"]
    )

    # Apply trend first.
    trend_adjusted = (
        baseline
        * growth_factor
    )

    # Then seasonality.
    final_forecast = (
        apply_seasonality(
            forecast=trend_adjusted,
            seasonal_factor=seasonal_factor,
        )
    )

    trend_class = (
        classify_trend(
            growth_factor
        )
    )

    seasonality_explanation = (
        build_seasonality_explanation(
            seasonal_factor=seasonal_factor,
            source=seasonality_source,
            month_number=month_number,
        )
    )

    explanation = (
        build_forecast_explanation(
            baseline=baseline,
            growth_factor=growth_factor,
            seasonal_factor=seasonal_factor,
            forecast=final_forecast,
            trend_class=trend_class,
            seasonality_explanation=
                seasonality_explanation,
        )
    )

    return {
        "sku": sku,
        "forecast_month": target_month,
        "baseline_demand":
            float(baseline),
        "growth_factor":
            float(growth_factor),
        "trend_class":
            trend_class,
        "seasonal_factor":
            float(seasonal_factor),
        "seasonality_source":
            seasonality_source,
        "forecast":
            float(final_forecast),
        "forecast_explanation":
            explanation,
    }


def forecast_next_months(
    demand: pd.DataFrame,
    seasonality_model: dict,
    months_ahead: int = 3,
    baseline_window: int = 3,
    trend_window: int = 6,
) -> pd.DataFrame:
    """
    Complete forecasting pipeline.

    For every SKU:

        cleaned/corrected demand
                ↓
        recent baseline
                ↓
        recent trend
                ↓
        seasonal adjustment
                ↓
        monthly forecast

    Forecasts multiple future months.
    """

    if months_ahead < 1:
        raise ValueError(
            "months_ahead must be at least 1"
        )

    history = (
        prepare_forecast_history(
            demand
        )
    )

    if history.empty:

        return pd.DataFrame(
            columns=[
                "sku",
                "forecast_month",
                "baseline_demand",
                "growth_factor",
                "trend_class",
                "seasonal_factor",
                "seasonality_source",
                "forecast",
                "forecast_explanation",
            ]
        )

    baselines = (
        calculate_baseline(
            history,
            window=baseline_window,
        )
    )

    trends = (
        calculate_growth_factor(
            history,
            trend_window=trend_window,
        )
    )

    variability = (
        calculate_demand_variability(
            history,
            window=trend_window,
        )
    )

    sku_parameters = (
        baselines
        .merge(
            trends,
            on="sku",
            how="left",
        )
        .merge(
            variability,
            on="sku",
            how="left",
        )
    )

    last_month = (
        history["month"].max()
    )

    results = []

    for _, row in (
        sku_parameters.iterrows()
    ):

        sku = row["sku"]

        baseline = float(
            row["baseline_demand"]
        )

        growth_factor = float(
            row["growth_factor"]
        )

        for step in range(
            1,
            months_ahead + 1,
        ):

            target_month = (
                last_month
                + pd.DateOffset(
                    months=step
                )
            )

            result = (
                forecast_single_sku(
                    sku=sku,
                    target_month=target_month,
                    baseline=baseline,
                    growth_factor=growth_factor,
                    seasonality_model=
                        seasonality_model,
                )
            )

            result["demand_std"] = float(
                row.get(
                    "demand_std",
                    0.0,
                )
            )

            result[
                "coefficient_of_variation"
            ] = float(
                row.get(
                    "coefficient_of_variation",
                    0.0,
                )
            )

            results.append(
                result
            )

    forecasts = pd.DataFrame(
        results
    )

    return forecasts.sort_values(
        [
            "sku",
            "forecast_month",
        ]
    ).reset_index(drop=True)


def get_forecast_summary(
    forecasts: pd.DataFrame,
) -> pd.DataFrame:
    """
    Produce one forecast summary per SKU.

    Useful for recommendation calculation.
    """

    required = {
        "sku",
        "forecast",
        "demand_std",
    }

    missing = required - set(
        forecasts.columns
    )

    if missing:
        raise ValueError(
            "Missing forecast columns: "
            + ", ".join(sorted(missing))
        )

    summary = (
        forecasts
        .groupby(
            "sku",
            as_index=False,
        )
        .agg(
            total_forecast=(
                "forecast",
                "sum",
            ),
            average_monthly_forecast=(
                "forecast",
                "mean",
            ),
            demand_std=(
                "demand_std",
                "first",
            ),
        )
    )

    return summary