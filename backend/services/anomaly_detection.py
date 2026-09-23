import numpy as np
import pandas as pd


def calculate_iqr_bounds(
    values: pd.Series,
    multiplier: float = 1.5,
) -> tuple[float, float]:
    """
    Calculate classic IQR anomaly boundaries.
    """

    clean = pd.to_numeric(values, errors="coerce").dropna()

    if len(clean) < 4:
        return -np.inf, np.inf

    q1 = clean.quantile(0.25)
    q3 = clean.quantile(0.75)

    iqr = q3 - q1

    if iqr == 0:
        return -np.inf, np.inf

    lower = q1 - multiplier * iqr
    upper = q3 + multiplier * iqr

    return float(lower), float(upper)


def add_document_features(
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """
    Add document-level concentration features.

    IMPORTANT:
    The provided IEK source data does not contain client_id.
    Therefore document_number is used only as a transaction/document
    concentration proxy.

    document_share must NOT be described as real client concentration.
    """

    df = sales.copy()

    if "document_number" not in df.columns:
        df["document_share"] = np.nan
        df["document_total"] = np.nan
        return df

    # Total SKU demand during the week
    period_total = (
        df.groupby(["sku", "week"])["quantity"]
        .transform("sum")
    )

    # How much of that demand came from one document
    document_total = (
        df.groupby(
            ["sku", "week", "document_number"]
        )["quantity"]
        .transform("sum")
    )

    df["document_total"] = document_total

    df["document_share"] = np.where(
        period_total > 0,
        document_total / period_total,
        0.0,
    )

    return df


def add_sku_order_features(
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """
    Calculate transaction-size features for every SKU.
    """

    df = sales.copy()

    df["sku_median_order"] = (
        df.groupby("sku")["quantity"]
        .transform("median")
    )

    df["sku_mean_order"] = (
        df.groupby("sku")["quantity"]
        .transform("mean")
    )

    df["sku_std_order"] = (
        df.groupby("sku")["quantity"]
        .transform("std")
        .fillna(0)
    )

    df["median_ratio"] = np.where(
        df["sku_median_order"] > 0,
        df["quantity"] / df["sku_median_order"],
        1.0,
    )

    return df


def add_iqr_flags(
    sales: pd.DataFrame,
    multiplier: float = 1.5,
) -> pd.DataFrame:
    """
    Detect unusually large transactions using SKU-level IQR.
    """

    df = sales.copy()

    df["iqr_lower"] = -np.inf
    df["iqr_upper"] = np.inf
    df["iqr_outlier"] = False

    for sku, indexes in df.groupby("sku").groups.items():

        values = df.loc[indexes, "quantity"]

        lower, upper = calculate_iqr_bounds(
            values,
            multiplier=multiplier,
        )

        df.loc[indexes, "iqr_lower"] = lower
        df.loc[indexes, "iqr_upper"] = upper

        # We care mainly about unusually LARGE sales.
        df.loc[indexes, "iqr_outlier"] = (
            df.loc[indexes, "quantity"] > upper
        )

    return df


def add_concentration_flags(
    sales: pd.DataFrame,
    threshold: float = 0.80,
) -> pd.DataFrame:
    """
    Flag cases where one document accounts for a very large
    share of weekly SKU demand.

    This is only a document concentration proxy.
    """

    df = sales.copy()

    if "document_share" not in df.columns:
        df["concentration_flag"] = False
        return df

    df["concentration_flag"] = (
        df["document_share"]
        .fillna(0)
        .ge(threshold)
    )

    return df


def add_large_order_flags(
    sales: pd.DataFrame,
    median_ratio_threshold: float = 3.0,
) -> pd.DataFrame:
    """
    Flag transactions much larger than the typical transaction
    for the same SKU.
    """

    df = sales.copy()

    df["large_vs_median"] = (
        df["median_ratio"]
        .fillna(1.0)
        .ge(median_ratio_threshold)
    )

    return df


def classify_transaction_anomalies(
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """
    Combine anomaly signals into an explainable classification.

    Possible classifications:
    - normal
    - review
    - potential_one_off

    Structural persistence is handled separately in
    structural_shift.py.
    """

    df = sales.copy()

    # Count how many anomaly signals fired.
    df["anomaly_signal_count"] = (
        df["iqr_outlier"].astype(int)
        + df["large_vs_median"].astype(int)
        + df["concentration_flag"].astype(int)
    )

    df["anomaly_class"] = "normal"

    # One signal -> suspicious, but not enough evidence
    df.loc[
        df["anomaly_signal_count"] == 1,
        "anomaly_class",
    ] = "review"

    # Two or more independent signals -> potential one-off
    df.loc[
        df["anomaly_signal_count"] >= 2,
        "anomaly_class",
    ] = "potential_one_off"

    return df


def build_anomaly_reason(row: pd.Series) -> str:
    """
    Generate a human-readable explanation for the anomaly.
    """

    reasons = []

    if bool(row.get("iqr_outlier", False)):
        reasons.append(
            "transaction quantity exceeds the SKU IQR threshold"
        )

    if bool(row.get("large_vs_median", False)):
        ratio = row.get("median_ratio")

        if pd.notna(ratio):
            reasons.append(
                f"transaction is {ratio:.1f}x the SKU median order"
            )

    if bool(row.get("concentration_flag", False)):
        share = row.get("document_share")

        if pd.notna(share):
            reasons.append(
                f"document represents {share:.0%} of weekly SKU demand"
            )

    if not reasons:
        return "no anomaly signals"

    return "; ".join(reasons)


def detect_transaction_anomalies(
    sales: pd.DataFrame,
    iqr_multiplier: float = 1.5,
    median_ratio_threshold: float = 3.0,
    concentration_threshold: float = 0.80,
) -> pd.DataFrame:
    """
    Complete transaction-level anomaly detection pipeline.

    Steps:
    1. Document concentration proxy
    2. SKU transaction statistics
    3. IQR anomaly detection
    4. Large-order detection
    5. Document concentration detection
    6. Explainable anomaly classification

    IMPORTANT:
    'potential_one_off' does NOT automatically mean that the
    transaction should be removed from demand.

    Persistence must first be checked by structural_shift.py.
    """

    required_columns = {
        "sku",
        "quantity",
        "week",
    }

    missing = required_columns - set(sales.columns)

    if missing:
        raise ValueError(
            "Missing columns for anomaly detection: "
            + ", ".join(sorted(missing))
        )

    df = sales.copy()

    # Make sure quantity is numeric.
    df["quantity"] = pd.to_numeric(
        df["quantity"],
        errors="coerce",
    )

    # Invalid quantities cannot participate in anomaly detection.
    df = df.dropna(
        subset=["sku", "quantity", "week"]
    ).copy()

    # 1. Document concentration proxy
    df = add_document_features(df)

    # 2. SKU-level order statistics
    df = add_sku_order_features(df)

    # 3. IQR
    df = add_iqr_flags(
        df,
        multiplier=iqr_multiplier,
    )

    # 4. Large compared with normal transaction
    df = add_large_order_flags(
        df,
        median_ratio_threshold=median_ratio_threshold,
    )

    # 5. Concentration
    df = add_concentration_flags(
        df,
        threshold=concentration_threshold,
    )

    # 6. Final transaction-level classification
    df = classify_transaction_anomalies(df)

    # Explanation for frontend
    df["anomaly_reason"] = df.apply(
        build_anomaly_reason,
        axis=1,
    )

    return df