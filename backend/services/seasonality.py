import numpy as np
import pandas as pd


MONTH_NAMES_RU = {
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


MONTH_NUMBER_BY_NAME = {
    "янв": 1,
    "январь": 1,
    "фев": 2,
    "февраль": 2,
    "мар": 3,
    "март": 3,
    "апр": 4,
    "апрель": 4,
    "май": 5,
    "июн": 6,
    "июнь": 6,
    "июл": 7,
    "июль": 7,
    "авг": 8,
    "август": 8,
    "сен": 9,
    "сент": 9,
    "сентябрь": 9,
    "окт": 10,
    "октябрь": 10,
    "ноя": 11,
    "ноябрь": 11,
    "дек": 12,
    "декабрь": 12,
}


def normalize_month_name(
    value,
) -> str | None:
    """
    Normalize Russian month names.

    Examples:
        'ЯНВ' -> 'янв'
        'сент.' -> 'сент'
        ' август ' -> 'август'
    """

    if pd.isna(value):
        return None

    text = str(value).strip().lower()

    text = text.replace(".", "")

    return text


def month_name_to_number(
    value,
) -> int | None:
    """
    Convert Russian month name to month number.
    """

    normalized = normalize_month_name(value)

    if normalized is None:
        return None

    return MONTH_NUMBER_BY_NAME.get(normalized)


def prepare_external_seasonality(
    seasonality: pd.DataFrame,
) -> pd.DataFrame:
    """
    Normalize externally provided seasonality coefficients.

    Expected normalized input columns:

        month
        seasonal_factor

    month may be:
        1
        2
        ...
        12

    or Russian month names:
        янв
        фев
        мар
        ...
    """

    required = {
        "month",
        "seasonal_factor",
    }

    missing = required - set(seasonality.columns)

    if missing:
        raise ValueError(
            "Missing seasonality columns: "
            + ", ".join(sorted(missing))
        )

    df = seasonality.copy()

    # Try numeric month first.
    numeric_month = pd.to_numeric(
        df["month"],
        errors="coerce",
    )

    # Convert Russian names when month is not numeric.
    named_month = df["month"].apply(
        month_name_to_number
    )

    df["month_number"] = numeric_month

    df["month_number"] = (
        df["month_number"]
        .fillna(named_month)
    )

    df["month_number"] = pd.to_numeric(
        df["month_number"],
        errors="coerce",
    )

    df["seasonal_factor"] = (
        df["seasonal_factor"]
        .astype(str)
        .str.replace(" ", "", regex=False)
        .str.replace(",", ".", regex=False)
    )

    df["seasonal_factor"] = pd.to_numeric(
        df["seasonal_factor"],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "month_number",
            "seasonal_factor",
        ]
    ).copy()

    df["month_number"] = (
        df["month_number"].astype(int)
    )

    df = df[
        df["month_number"].between(1, 12)
    ]

    # Invalid factors should not influence forecast.
    df = df[
        df["seasonal_factor"] > 0
    ]

    # If the source contains several values for the same month,
    # use their median.
    df = (
        df.groupby(
            "month_number",
            as_index=False,
        )["seasonal_factor"]
        .median()
    )

    df["month_name"] = (
        df["month_number"]
        .map(MONTH_NAMES_RU)
    )

    df["seasonality_source"] = "provided"

    return df


def prepare_monthly_demand(
    demand: pd.DataFrame,
) -> pd.DataFrame:
    """
    Convert demand history into monthly demand per SKU.

    Supported input:

    1. Transaction-level:
        sku
        date
        quantity

    OR

    2. Corrected stockout output:
        sku
        month
        corrected_demand
    """

    df = demand.copy()

    if {
        "sku",
        "month",
        "corrected_demand",
    }.issubset(df.columns):

        df["month"] = pd.to_datetime(
            df["month"],
            errors="coerce",
        )

        df["demand"] = pd.to_numeric(
            df["corrected_demand"],
            errors="coerce",
        )

        result = (
            df.dropna(
                subset=[
                    "sku",
                    "month",
                    "demand",
                ]
            )
            .groupby(
                ["sku", "month"],
                as_index=False,
            )["demand"]
            .sum()
        )

        return result

    required = {
        "sku",
        "date",
        "quantity",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            "Demand data must contain either "
            "{sku, month, corrected_demand} "
            "or {sku, date, quantity}. "
            "Missing: "
            + ", ".join(sorted(missing))
        )

    df["date"] = pd.to_datetime(
        df["date"],
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
            "quantity",
        ]
    ).copy()

    df["month"] = (
        df["date"]
        .dt.to_period("M")
        .dt.to_timestamp()
    )

    result = (
        df.groupby(
            ["sku", "month"],
            as_index=False,
        )["quantity"]
        .sum()
        .rename(
            columns={
                "quantity": "demand"
            }
        )
    )

    return result


def calculate_global_seasonality(
    monthly_demand: pd.DataFrame,
) -> pd.DataFrame:
    """
    Calculate overall seasonality from historical demand.

    seasonal factor =
        average demand for month
        /
        overall average monthly demand

    Factor:
        > 1 -> stronger-than-average month
        < 1 -> weaker-than-average month
    """

    required = {
        "sku",
        "month",
        "demand",
    }

    missing = required - set(
        monthly_demand.columns
    )

    if missing:
        raise ValueError(
            "Missing monthly demand columns: "
            + ", ".join(sorted(missing))
        )

    df = monthly_demand.copy()

    df["month"] = pd.to_datetime(
        df["month"],
        errors="coerce",
    )

    df["demand"] = pd.to_numeric(
        df["demand"],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "month",
            "demand",
        ]
    )

    df["month_number"] = (
        df["month"].dt.month
    )

    monthly_average = (
        df.groupby("month_number")["demand"]
        .mean()
    )

    overall_average = df["demand"].mean()

    if (
        pd.isna(overall_average)
        or overall_average <= 0
    ):
        return pd.DataFrame(
            {
                "month_number": range(1, 13),
                "seasonal_factor": [1.0] * 12,
                "seasonality_source": [
                    "fallback_neutral"
                ] * 12,
            }
        )

    factors = (
        monthly_average
        / overall_average
    )

    result = factors.reset_index()

    result.columns = [
        "month_number",
        "seasonal_factor",
    ]

    # Normalize factors so their average is approximately 1.
    factor_mean = (
        result["seasonal_factor"].mean()
    )

    if (
        pd.notna(factor_mean)
        and factor_mean > 0
    ):
        result["seasonal_factor"] = (
            result["seasonal_factor"]
            / factor_mean
        )

    result["month_name"] = (
        result["month_number"]
        .map(MONTH_NAMES_RU)
    )

    result["seasonality_source"] = (
        "calculated_global"
    )

    return result


def calculate_sku_seasonality(
    monthly_demand: pd.DataFrame,
    minimum_months: int = 12,
) -> pd.DataFrame:
    """
    Calculate SKU-specific seasonality.

    SKU-specific seasonality is used only when enough
    historical data exists.

    Returns:
        sku
        month_number
        seasonal_factor
        history_months
    """

    required = {
        "sku",
        "month",
        "demand",
    }

    missing = required - set(
        monthly_demand.columns
    )

    if missing:
        raise ValueError(
            "Missing monthly demand columns: "
            + ", ".join(sorted(missing))
        )

    df = monthly_demand.copy()

    df["month"] = pd.to_datetime(
        df["month"],
        errors="coerce",
    )

    df["demand"] = pd.to_numeric(
        df["demand"],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "sku",
            "month",
            "demand",
        ]
    )

    df["month_number"] = (
        df["month"].dt.month
    )

    results = []

    for sku, group in df.groupby("sku"):

        history_months = (
            group["month"].nunique()
        )

        if history_months < minimum_months:
            continue

        overall_average = (
            group["demand"].mean()
        )

        if (
            pd.isna(overall_average)
            or overall_average <= 0
        ):
            continue

        by_month = (
            group.groupby(
                "month_number"
            )["demand"]
            .mean()
        )

        factors = (
            by_month
            / overall_average
        )

        # Normalize available factors around 1.
        if (
            len(factors) > 0
            and factors.mean() > 0
        ):
            factors = (
                factors / factors.mean()
            )

        for month_number, factor in (
            factors.items()
        ):

            results.append(
                {
                    "sku": sku,
                    "month_number":
                        int(month_number),
                    "seasonal_factor":
                        float(factor),
                    "history_months":
                        int(history_months),
                    "seasonality_source":
                        "calculated_sku",
                }
            )

    if not results:
        return pd.DataFrame(
            columns=[
                "sku",
                "month_number",
                "seasonal_factor",
                "history_months",
                "seasonality_source",
            ]
        )

    return pd.DataFrame(results)


def build_seasonality_model(
    demand: pd.DataFrame,
    provided_seasonality: pd.DataFrame | None = None,
    minimum_sku_months: int = 12,
) -> dict:
    """
    Build all available seasonality models.

    Priority later will be:

        SKU-specific calculated factor
            ↓
        externally provided IEK factor
            ↓
        global calculated factor
            ↓
        neutral factor 1.0
    """

    monthly_demand = prepare_monthly_demand(
        demand
    )

    global_factors = (
        calculate_global_seasonality(
            monthly_demand
        )
    )

    sku_factors = (
        calculate_sku_seasonality(
            monthly_demand,
            minimum_months=minimum_sku_months,
        )
    )

    if provided_seasonality is not None:

        provided_factors = (
            prepare_external_seasonality(
                provided_seasonality
            )
        )

    else:

        provided_factors = pd.DataFrame(
            columns=[
                "month_number",
                "seasonal_factor",
                "month_name",
                "seasonality_source",
            ]
        )

    return {
        "monthly_demand": monthly_demand,
        "sku_factors": sku_factors,
        "provided_factors": provided_factors,
        "global_factors": global_factors,
    }


def get_seasonal_factor(
    sku: str,
    month_number: int,
    seasonality_model: dict,
) -> dict:
    """
    Get the best available seasonal factor.

    Priority:
    1. SKU-specific factor
    2. Provided IEK factor
    3. Global calculated factor
    4. Neutral 1.0
    """

    if month_number < 1 or month_number > 12:
        raise ValueError(
            "month_number must be between 1 and 12"
        )

    sku_factors = seasonality_model.get(
        "sku_factors",
        pd.DataFrame(),
    )

    provided = seasonality_model.get(
        "provided_factors",
        pd.DataFrame(),
    )

    global_factors = seasonality_model.get(
        "global_factors",
        pd.DataFrame(),
    )

    # 1. SKU-specific
    if not sku_factors.empty:

        match = sku_factors[
            (sku_factors["sku"] == sku)
            & (
                sku_factors["month_number"]
                == month_number
            )
        ]

        if not match.empty:

            row = match.iloc[0]

            return {
                "seasonal_factor":
                    float(
                        row["seasonal_factor"]
                    ),
                "source":
                    "calculated_sku",
            }

    # 2. Provided IEK seasonality
    if not provided.empty:

        match = provided[
            provided["month_number"]
            == month_number
        ]

        if not match.empty:

            row = match.iloc[0]

            return {
                "seasonal_factor":
                    float(
                        row["seasonal_factor"]
                    ),
                "source":
                    "provided",
            }

    # 3. Global calculated
    if not global_factors.empty:

        match = global_factors[
            global_factors["month_number"]
            == month_number
        ]

        if not match.empty:

            row = match.iloc[0]

            return {
                "seasonal_factor":
                    float(
                        row["seasonal_factor"]
                    ),
                "source":
                    "calculated_global",
            }

    # 4. No information
    return {
        "seasonal_factor": 1.0,
        "source": "neutral",
    }


def apply_seasonality(
    forecast: float,
    seasonal_factor: float,
) -> float:
    """
    Apply seasonality to a baseline forecast.

    Example:
        forecast = 100
        factor = 1.20

        result = 120
    """

    if pd.isna(forecast):
        return 0.0

    if pd.isna(seasonal_factor):
        seasonal_factor = 1.0

    forecast = max(
        0.0,
        float(forecast),
    )

    seasonal_factor = max(
        0.0,
        float(seasonal_factor),
    )

    return (
        forecast
        * seasonal_factor
    )


def build_seasonality_explanation(
    seasonal_factor: float,
    source: str,
    month_number: int,
) -> str:
    """
    Generate explanation for API/frontend.
    """

    month_name = MONTH_NAMES_RU.get(
        month_number,
        str(month_number),
    )

    if seasonal_factor > 1.05:

        impact = (
            f"seasonal demand is "
            f"{(seasonal_factor - 1) * 100:.1f}% "
            f"above normal"
        )

    elif seasonal_factor < 0.95:

        impact = (
            f"seasonal demand is "
            f"{(1 - seasonal_factor) * 100:.1f}% "
            f"below normal"
        )

    else:

        impact = (
            "seasonality is close to normal"
        )

    return (
        f"{month_name}: seasonal factor "
        f"{seasonal_factor:.2f}; "
        f"{impact}; source={source}"
    )