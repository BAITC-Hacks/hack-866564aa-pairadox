import numpy as np
import pandas as pd


def normalize_month(
    values: pd.Series,
) -> pd.Series:
    """
    Convert values to the first day of their month.

    Example:
        2026-09-23 -> 2026-09-01
    """

    dates = pd.to_datetime(
        values,
        errors="coerce",
    )

    return dates.dt.to_period("M").dt.to_timestamp()


def prepare_inventory_history(
    inventory: pd.DataFrame,
) -> pd.DataFrame:
    """
    Validate and clean monthly inventory history.

    Expected columns:
        sku
        month
        stock
    """

    required = {
        "sku",
        "month",
        "stock",
    }

    missing = required - set(inventory.columns)

    if missing:
        raise ValueError(
            "Missing inventory columns: "
            + ", ".join(sorted(missing))
        )

    df = inventory.copy()

    df["sku"] = (
        df["sku"]
        .astype(str)
        .str.strip()
        .str.replace("_", "", regex=False)
    )

    df["month"] = normalize_month(
        df["month"]
    )

    df["stock"] = pd.to_numeric(
        df["stock"],
        errors="coerce",
    )

    df = df.dropna(
        subset=["sku", "month"]
    ).copy()

    df["stock"] = df["stock"].fillna(0)

    df = (
        df.groupby(
            ["sku", "month"],
            as_index=False,
        )["stock"]
        .last()
    )

    return df.sort_values(
        ["sku", "month"]
    ).reset_index(drop=True)


def prepare_monthly_sales(
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """
    Aggregate transaction-level sales into monthly SKU demand.

    Expected sales columns:
        sku
        date
        quantity
    """

    required = {
        "sku",
        "date",
        "quantity",
    }

    missing = required - set(sales.columns)

    if missing:
        raise ValueError(
            "Missing sales columns: "
            + ", ".join(sorted(missing))
        )

    df = sales.copy()

    df["sku"] = (
        df["sku"]
        .astype(str)
        .str.strip()
        .str.replace("_", "", regex=False)
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

    monthly = (
        df.groupby(
            ["sku", "month"],
            as_index=False,
        )["quantity"]
        .sum()
        .rename(
            columns={
                "quantity": "actual_demand"
            }
        )
    )

    return monthly


def combine_sales_and_inventory(
    monthly_sales: pd.DataFrame,
    inventory: pd.DataFrame,
) -> pd.DataFrame:
    """
    Combine monthly demand with monthly inventory.

    Outer merge is intentional:
    a month with inventory but no sales is still useful,
    and a month with sales but missing inventory must not disappear.
    """

    merged = pd.merge(
        monthly_sales,
        inventory,
        on=["sku", "month"],
        how="outer",
    )

    merged["actual_demand"] = (
        pd.to_numeric(
            merged["actual_demand"],
            errors="coerce",
        )
        .fillna(0)
    )

    merged["stock"] = pd.to_numeric(
        merged["stock"],
        errors="coerce",
    )

    return merged.sort_values(
        ["sku", "month"]
    ).reset_index(drop=True)


def calculate_reference_demand(
    data: pd.DataFrame,
    window: int = 3,
) -> pd.DataFrame:
    """
    Estimate normal monthly demand using previous months.

    IMPORTANT:
    Only historical months are used.
    Current month is excluded using shift(1).

    Median is used instead of mean because it is more robust
    against one unusually large sales month.
    """

    df = data.copy()

    df["reference_demand"] = (
        df.groupby("sku")["actual_demand"]
        .transform(
            lambda series:
            series
            .shift(1)
            .rolling(
                window=window,
                min_periods=2,
            )
            .median()
        )
    )

    return df


def add_inventory_context(
    data: pd.DataFrame,
) -> pd.DataFrame:
    """
    Add previous and next known monthly stock.

    These features help distinguish suspicious low-stock periods
    from normal low-demand periods.
    """

    df = data.copy()

    df["previous_stock"] = (
        df.groupby("sku")["stock"]
        .shift(1)
    )

    df["next_stock"] = (
        df.groupby("sku")["stock"]
        .shift(-1)
    )

    return df


def detect_stockout_risk(
    data: pd.DataFrame,
    low_stock_ratio: float = 0.25,
) -> pd.DataFrame:
    """
    Detect likely stock-constrained months.

    Because the supplied IEK inventory file contains monthly
    beginning balances rather than exact daily stockout intervals,
    this function identifies stockout RISK / likely constrained
    periods rather than claiming an exact stockout duration.

    Signals:
    1. stock <= 0
    2. stock is very small relative to expected monthly demand
    3. sales are abnormally low while stock is also low
    """

    df = data.copy()

    df["zero_stock_flag"] = (
        df["stock"].notna()
        & df["stock"].le(0)
    )

    df["low_stock_flag"] = (
        df["stock"].notna()
        & df["reference_demand"].notna()
        & df["reference_demand"].gt(0)
        & (
            df["stock"]
            <= (
                df["reference_demand"]
                * low_stock_ratio
            )
        )
    )

    df["low_sales_flag"] = (
        df["reference_demand"].notna()
        & df["reference_demand"].gt(0)
        & (
            df["actual_demand"]
            < df["reference_demand"] * 0.50
        )
    )

    df["stockout_risk"] = (
        df["zero_stock_flag"]
        | (
            df["low_stock_flag"]
            & df["low_sales_flag"]
        )
    )

    return df


def estimate_lost_demand(
    data: pd.DataFrame,
) -> pd.DataFrame:
    """
    Estimate demand potentially hidden by inventory shortage.

    We do NOT invent exact stockout days because the source data
    does not contain daily stock levels.

    Estimated lost demand is therefore:

        max(reference demand - actual demand, 0)

    only for months identified as stockout-risk periods.
    """

    df = data.copy()

    gap = (
        df["reference_demand"]
        - df["actual_demand"]
    )

    df["estimated_lost_demand"] = np.where(
        df["stockout_risk"]
        & df["reference_demand"].notna(),

        np.maximum(
            gap,
            0,
        ),

        0.0,
    )

    return df


def calculate_corrected_demand(
    data: pd.DataFrame,
) -> pd.DataFrame:
    """
    Create demand series corrected for likely inventory shortages.

    corrected demand =
        actual demand
        + estimated lost demand
    """

    df = data.copy()

    df["corrected_demand"] = (
        df["actual_demand"]
        + df["estimated_lost_demand"]
    )

    return df


def calculate_stock_coverage(
    data: pd.DataFrame,
) -> pd.DataFrame:
    """
    Estimate how much of expected monthly demand could be
    covered by beginning inventory.

    Example:
        stock = 20
        expected demand = 100

        coverage_ratio = 0.20
    """

    df = data.copy()

    df["stock_coverage_ratio"] = np.where(
        df["reference_demand"] > 0,
        df["stock"]
        / df["reference_demand"],
        np.nan,
    )

    return df


def classify_stockout_risk(
    row: pd.Series,
) -> str:
    """
    Convert stockout signals into a readable classification.
    """

    if bool(
        row.get(
            "zero_stock_flag",
            False,
        )
    ):
        return "high"

    if bool(
        row.get(
            "stockout_risk",
            False,
        )
    ):
        return "medium"

    return "low"


def build_stockout_reason(
    row: pd.Series,
) -> str:
    """
    Generate an explainable reason for the frontend.
    """

    risk = row.get(
        "stockout_risk_level",
        "low",
    )

    stock = row.get("stock")
    actual = row.get("actual_demand")
    expected = row.get("reference_demand")
    lost = row.get("estimated_lost_demand")

    if risk == "high":

        text = (
            "beginning inventory was zero or negative"
        )

        if (
            pd.notna(expected)
            and pd.notna(actual)
        ):
            text += (
                f"; actual demand {actual:.1f}, "
                f"historical reference {expected:.1f}"
            )

        if pd.notna(lost) and lost > 0:
            text += (
                f"; estimated hidden demand "
                f"{lost:.1f} units"
            )

        return text

    if risk == "medium":

        text = (
            "inventory was low and observed demand "
            "was below historical reference"
        )

        if pd.notna(stock):
            text += f"; beginning stock {stock:.1f}"

        if pd.notna(expected):
            text += (
                f"; reference demand {expected:.1f}"
            )

        if pd.notna(lost) and lost > 0:
            text += (
                f"; estimated hidden demand "
                f"{lost:.1f} units"
            )

        return text

    return (
        "no strong evidence of inventory-constrained demand"
    )


def reconstruct_stockout_demand(
    sales: pd.DataFrame,
    inventory: pd.DataFrame,
    reference_window: int = 3,
    low_stock_ratio: float = 0.25,
) -> pd.DataFrame:
    """
    Complete stockout-demand reconstruction pipeline.

    Pipeline:

        transaction sales
              ↓
        monthly actual demand

        monthly inventory
              ↓

        merge sales + inventory
              ↓
        historical reference demand
              ↓
        detect likely inventory constraint
              ↓
        estimate hidden demand
              ↓
        corrected demand

    IMPORTANT:
    IEK source data provides monthly beginning inventory,
    not exact daily stockout periods.

    Therefore:
    - stockout_risk is an inference
    - estimated_lost_demand is an estimate
    - we must NOT claim exact stockout days
    """

    if reference_window < 2:
        raise ValueError(
            "reference_window must be at least 2"
        )

    if not 0 < low_stock_ratio <= 1:
        raise ValueError(
            "low_stock_ratio must be between 0 and 1"
        )

    # 1. Prepare monthly demand.
    monthly_sales = prepare_monthly_sales(
        sales
    )

    # 2. Prepare monthly inventory.
    inventory_clean = (
        prepare_inventory_history(
            inventory
        )
    )

    # 3. Combine both datasets.
    combined = combine_sales_and_inventory(
        monthly_sales,
        inventory_clean,
    )

    # 4. Calculate normal historical demand.
    combined = calculate_reference_demand(
        combined,
        window=reference_window,
    )

    # 5. Add neighboring inventory information.
    combined = add_inventory_context(
        combined
    )

    # 6. Calculate stock coverage.
    combined = calculate_stock_coverage(
        combined
    )

    # 7. Detect likely stockout periods.
    combined = detect_stockout_risk(
        combined,
        low_stock_ratio=low_stock_ratio,
    )

    # 8. Estimate demand hidden by shortage.
    combined = estimate_lost_demand(
        combined
    )

    # 9. Correct demand.
    combined = calculate_corrected_demand(
        combined
    )

    # 10. Risk classification.
    combined["stockout_risk_level"] = (
        combined.apply(
            classify_stockout_risk,
            axis=1,
        )
    )

    # 11. Explanation for frontend.
    combined["stockout_reason"] = (
        combined.apply(
            build_stockout_reason,
            axis=1,
        )
    )

    return combined


def get_stockout_summary(
    stockout_results: pd.DataFrame,
) -> pd.DataFrame:
    """
    Create one stockout summary row per SKU.

    Useful later when building recommendation API responses.
    """

    required = {
        "sku",
        "stockout_risk",
        "estimated_lost_demand",
        "corrected_demand",
    }

    missing = required - set(
        stockout_results.columns
    )

    if missing:
        raise ValueError(
            "Missing stockout result columns: "
            + ", ".join(sorted(missing))
        )

    summary = (
        stockout_results
        .groupby("sku", as_index=False)
        .agg(
            stockout_periods=(
                "stockout_risk",
                "sum",
            ),
            total_estimated_lost_demand=(
                "estimated_lost_demand",
                "sum",
            ),
            corrected_demand_total=(
                "corrected_demand",
                "sum",
            ),
        )
    )

    summary["has_stockout_risk"] = (
        summary["stockout_periods"] > 0
    )

    return summary