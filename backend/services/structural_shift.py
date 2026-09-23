import numpy as np
import pandas as pd


def aggregate_weekly_demand(
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """
    Aggregate transaction-level sales into weekly SKU demand.

    Returns:
        sku
        week
        weekly_demand
    """

    required = {"sku", "week", "quantity"}

    missing = required - set(sales.columns)

    if missing:
        raise ValueError(
            "Missing columns for weekly aggregation: "
            + ", ".join(sorted(missing))
        )

    df = sales.copy()

    df["quantity"] = pd.to_numeric(
        df["quantity"],
        errors="coerce",
    )

    df["week"] = pd.to_datetime(
        df["week"],
        errors="coerce",
    )

    df = df.dropna(
        subset=["sku", "week", "quantity"]
    )

    weekly = (
        df.groupby(
            ["sku", "week"],
            as_index=False,
        )["quantity"]
        .sum()
        .rename(
            columns={
                "quantity": "weekly_demand"
            }
        )
    )

    weekly = weekly.sort_values(
        ["sku", "week"]
    ).reset_index(drop=True)

    return weekly


def calculate_previous_baseline(
    values: pd.Series,
    window: int = 4,
) -> pd.Series:
    """
    Calculate historical baseline using only PREVIOUS weeks.

    shift(1) is important:
    the current week must not influence its own baseline.
    """

    return (
        values
        .shift(1)
        .rolling(
            window=window,
            min_periods=2,
        )
        .median()
    )


def add_baseline(
    weekly: pd.DataFrame,
    baseline_window: int = 4,
) -> pd.DataFrame:
    """
    Add rolling historical baseline for each SKU.
    """

    df = weekly.copy()

    df = df.sort_values(
        ["sku", "week"]
    ).reset_index(drop=True)

    df["baseline"] = (
        df.groupby("sku")["weekly_demand"]
        .transform(
            lambda series:
            calculate_previous_baseline(
                series,
                window=baseline_window,
            )
        )
    )

    return df


def add_demand_ratio(
    weekly: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compare current weekly demand with historical baseline.

    Example:
        baseline = 40
        demand = 60

        demand_ratio = 1.5
    """

    df = weekly.copy()

    df["demand_ratio"] = np.where(
        df["baseline"] > 0,
        df["weekly_demand"] / df["baseline"],
        np.nan,
    )

    return df


def detect_elevated_weeks(
    weekly: pd.DataFrame,
    shift_threshold: float = 1.25,
) -> pd.DataFrame:
    """
    Mark weeks where demand is meaningfully above baseline.

    Default:
        demand >= baseline * 1.25
    """

    df = weekly.copy()

    df["elevated"] = (
        df["demand_ratio"]
        .fillna(0)
        .ge(shift_threshold)
    )

    return df


def calculate_persistence(
    weekly: pd.DataFrame,
) -> pd.DataFrame:
    """
    Count consecutive elevated weeks for each SKU.

    Example:
        False False True True True False

    produces:
        0 0 1 2 3 0
    """

    df = weekly.copy()

    df["elevated_run"] = 0

    for sku, indexes in df.groupby("sku").groups.items():

        count = 0

        ordered_indexes = list(indexes)

        for index in ordered_indexes:

            if bool(df.at[index, "elevated"]):
                count += 1
            else:
                count = 0

            df.at[index, "elevated_run"] = count

    return df


def detect_structural_shifts(
    weekly: pd.DataFrame,
    persistence_weeks: int = 3,
) -> pd.DataFrame:
    """
    Detect sustained increases in demand.

    A structural shift is detected when demand remains
    elevated for several consecutive periods.
    """

    df = weekly.copy()

    df["structural_shift"] = (
        df["elevated_run"]
        >= persistence_weeks
    )

    return df


def mark_shift_periods(
    weekly: pd.DataFrame,
    persistence_weeks: int = 3,
) -> pd.DataFrame:
    """
    Once persistence is confirmed, mark the earlier elevated
    weeks belonging to the same run as structural-shift weeks.

    Example:

        demand:
        40 42 41 60 66 70

        elevated_run:
        0 0 0 1 2 3

    When week 3 confirms persistence, all three elevated
    weeks should belong to the structural shift.
    """

    df = weekly.copy()

    df["structural_shift_period"] = False

    for sku, group in df.groupby("sku"):

        indexes = list(group.index)

        run_indexes = []

        for index in indexes:

            if bool(df.at[index, "elevated"]):

                run_indexes.append(index)

            else:

                if len(run_indexes) >= persistence_weeks:
                    df.loc[
                        run_indexes,
                        "structural_shift_period",
                    ] = True

                run_indexes = []

        # Handle a run that continues until the final row
        if len(run_indexes) >= persistence_weeks:
            df.loc[
                run_indexes,
                "structural_shift_period",
            ] = True

    return df


def calculate_shift_size(
    weekly: pd.DataFrame,
) -> pd.DataFrame:
    """
    Estimate how much additional weekly demand is associated
    with a structural shift.
    """

    df = weekly.copy()

    df["shift_extra_demand"] = np.where(
        df["structural_shift_period"]
        & df["baseline"].notna(),

        np.maximum(
            0,
            df["weekly_demand"]
            - df["baseline"],
        ),

        0.0,
    )

    return df


def classify_week(
    row: pd.Series,
) -> str:
    """
    Human-readable week classification.
    """

    if bool(
        row.get(
            "structural_shift_period",
            False,
        )
    ):
        return "structural_shift"

    if bool(row.get("elevated", False)):
        return "temporary_spike"

    return "normal"


def build_shift_reason(
    row: pd.Series,
) -> str:
    """
    Generate explanation for frontend/API.
    """

    classification = row.get(
        "demand_class",
        "normal",
    )

    baseline = row.get("baseline")
    demand = row.get("weekly_demand")
    ratio = row.get("demand_ratio")
    run = row.get("elevated_run", 0)

    if classification == "structural_shift":

        if (
            pd.notna(baseline)
            and pd.notna(demand)
            and pd.notna(ratio)
        ):
            return (
                f"sustained demand increase: "
                f"weekly demand {demand:.1f} vs "
                f"baseline {baseline:.1f}; "
                f"{ratio:.2f}x baseline; "
                f"persistent elevated demand detected"
            )

        return "persistent elevated demand detected"

    if classification == "temporary_spike":

        if pd.notna(ratio):
            return (
                f"demand is temporarily elevated "
                f"({ratio:.2f}x baseline); "
                f"current elevated run: {int(run)} week(s)"
            )

        return "temporary demand spike"

    return "demand is within normal range"


def analyze_structural_shifts(
    sales: pd.DataFrame,
    baseline_window: int = 4,
    shift_threshold: float = 1.25,
    persistence_weeks: int = 3,
) -> pd.DataFrame:
    """
    Complete structural-shift detection pipeline.

    Pipeline:
        transactions
            ↓
        weekly SKU demand
            ↓
        previous historical baseline
            ↓
        demand / baseline ratio
            ↓
        elevated weeks
            ↓
        consecutive persistence
            ↓
        structural shift classification

    Parameters
    ----------
    baseline_window:
        Number of previous weeks used for baseline.

    shift_threshold:
        Demand must exceed baseline by this factor.

        1.25 means:
        demand >= 125% of baseline.

    persistence_weeks:
        Number of consecutive elevated weeks required
        before calling the pattern a structural shift.
    """

    if baseline_window < 2:
        raise ValueError(
            "baseline_window must be at least 2"
        )

    if shift_threshold <= 1:
        raise ValueError(
            "shift_threshold must be greater than 1"
        )

    if persistence_weeks < 2:
        raise ValueError(
            "persistence_weeks must be at least 2"
        )

    # 1. Aggregate transactions by week.
    weekly = aggregate_weekly_demand(sales)

    # 2. Historical baseline.
    weekly = add_baseline(
        weekly,
        baseline_window=baseline_window,
    )

    # 3. Compare demand with baseline.
    weekly = add_demand_ratio(weekly)

    # 4. Identify elevated periods.
    weekly = detect_elevated_weeks(
        weekly,
        shift_threshold=shift_threshold,
    )

    # 5. Calculate consecutive elevated weeks.
    weekly = calculate_persistence(weekly)

    # 6. Detect confirmation point.
    weekly = detect_structural_shifts(
        weekly,
        persistence_weeks=persistence_weeks,
    )

    # 7. Mark the complete persistent period.
    weekly = mark_shift_periods(
        weekly,
        persistence_weeks=persistence_weeks,
    )

    # 8. Estimate additional demand.
    weekly = calculate_shift_size(weekly)

    # 9. Final classification.
    weekly["demand_class"] = weekly.apply(
        classify_week,
        axis=1,
    )

    # 10. Explanation for frontend.
    weekly["shift_reason"] = weekly.apply(
        build_shift_reason,
        axis=1,
    )

    return weekly


def get_structural_shift_summary(
    structural_results: pd.DataFrame,
) -> pd.DataFrame:
    """
    Produce one summary row per SKU.

    Useful for the recommendation API.
    """

    required = {
        "sku",
        "week",
        "weekly_demand",
        "baseline",
        "structural_shift_period",
        "shift_extra_demand",
    }

    missing = required - set(
        structural_results.columns
    )

    if missing:
        raise ValueError(
            "Missing structural shift columns: "
            + ", ".join(sorted(missing))
        )

    summaries = []

    for sku, group in structural_results.groupby("sku"):

        group = group.sort_values("week")

        shifts = group[
            group["structural_shift_period"]
        ]

        has_shift = not shifts.empty

        if has_shift:

            latest_shift = shifts.iloc[-1]

            summaries.append(
                {
                    "sku": sku,
                    "has_structural_shift": True,
                    "latest_shift_week":
                        latest_shift["week"],
                    "latest_weekly_demand":
                        float(
                            latest_shift[
                                "weekly_demand"
                            ]
                        ),
                    "previous_baseline":
                        (
                            float(
                                latest_shift[
                                    "baseline"
                                ]
                            )
                            if pd.notna(
                                latest_shift[
                                    "baseline"
                                ]
                            )
                            else None
                        ),
                    "extra_weekly_demand":
                        float(
                            latest_shift[
                                "shift_extra_demand"
                            ]
                        ),
                }
            )

        else:

            summaries.append(
                {
                    "sku": sku,
                    "has_structural_shift": False,
                    "latest_shift_week": None,
                    "latest_weekly_demand": None,
                    "previous_baseline": None,
                    "extra_weekly_demand": 0.0,
                }
            )

    return pd.DataFrame(summaries)