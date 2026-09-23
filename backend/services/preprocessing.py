import re
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


MONTHS_RU = {
    "янв": 1,
    "фев": 2,
    "мар": 3,
    "март": 3,
    "апр": 4,
    "май": 5,
    "июн": 6,
    "июнь": 6,
    "июл": 7,
    "июль": 7,
    "авг": 8,
    "сен": 9,
    "сент": 9,
    "окт": 10,
    "ноя": 11,
    "нояб": 11,
    "дек": 12,
}


def clean_column_name(value) -> str:
    """Normalize Excel column names."""
    if pd.isna(value):
        return ""

    value = str(value)
    value = value.replace("\n", " ")
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def clean_sku(value) -> Optional[str]:
    """
    Normalize 1C SKU codes.

    Example:
        '030200874_' -> '030200874'
    """
    if pd.isna(value):
        return None

    value = str(value).strip()

    if value.endswith(".0"):
        value = value[:-2]

    value = value.rstrip("_")
    value = value.strip()

    if not value:
        return None

    return value


def clean_text(value) -> Optional[str]:
    """Clean ordinary text fields."""
    if pd.isna(value):
        return None

    value = str(value)
    value = value.replace("\xa0", " ")
    value = value.replace("\n", " ")
    value = re.sub(r"\s+", " ", value).strip()

    return value if value else None


def parse_number(value, default=np.nan):
    """
    Convert Russian-formatted Excel values to float.

    Handles:
        '19 723,000'
        '-10,000'
        '1 234.50'
        numeric Excel cells
    """
    if pd.isna(value):
        return default

    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)

    value = str(value).strip()

    if not value or value in {"-", "—", "–"}:
        return default

    value = value.replace("\xa0", "")
    value = value.replace(" ", "")
    value = value.replace(",", ".")

    value = re.sub(r"[^\d.\-]", "", value)

    if value in {"", "-", ".", "-."}:
        return default

    try:
        return float(value)
    except ValueError:
        return default


def detect_header_row(
    file_path: Path,
    required_words: list[str],
    max_rows: int = 30,
) -> int:
    """
    Finds the actual header row in messy Excel reports.
    """
    preview = pd.read_excel(
        file_path,
        header=None,
        nrows=max_rows,
        engine="openpyxl",
    )

    required_words = [word.lower() for word in required_words]

    for index, row in preview.iterrows():
        values = [
            clean_column_name(value).lower()
            for value in row.tolist()
            if not pd.isna(value)
        ]

        row_text = " | ".join(values)

        if all(word in row_text for word in required_words):
            return int(index)

    raise ValueError(
        f"Could not detect header in {file_path.name}. "
        f"Expected words: {required_words}"
    )


def load_sales_history(file_path: Path) -> pd.DataFrame:
    """
    Load transaction-level IEK sales history.
    """

    header_row = detect_header_row(
        file_path,
        required_words=["дата", "код", "количество"],
    )

    df = pd.read_excel(
        file_path,
        header=header_row,
        engine="openpyxl",
    )

    df.columns = [clean_column_name(column) for column in df.columns]

    rename_map = {
        "Дата": "date",
        "Номер": "document_number",
        "Документ": "document",
        "Код": "sku",
        "Номенклатура": "product_name",
        "Ед.": "unit",
        "Ед": "unit",
        "Склад": "warehouse",
        "Количество": "raw_quantity",
    }

    df = df.rename(
        columns={
            column: rename_map[column]
            for column in df.columns
            if column in rename_map
        }
    )

    required = {
        "date",
        "sku",
        "product_name",
        "raw_quantity",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Sales history is missing columns: {sorted(missing)}"
        )

    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce",
        dayfirst=True,
    )

    df["sku"] = df["sku"].apply(clean_sku)
    df["product_name"] = df["product_name"].apply(clean_text)

    if "warehouse" in df.columns:
        df["warehouse"] = df["warehouse"].apply(clean_text)

    if "unit" in df.columns:
        df["unit"] = df["unit"].apply(clean_text)

    df["raw_quantity"] = df["raw_quantity"].apply(parse_number)

    # In source data, расходные накладные are negative.
    # Demand should be positive.
    df["quantity"] = df["raw_quantity"].abs()

    df = df.dropna(
        subset=[
            "date",
            "sku",
            "quantity",
        ]
    )

    df = df[df["quantity"] > 0]

    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month

    # Monday of the corresponding week
    df["week"] = (
        df["date"]
        - pd.to_timedelta(df["date"].dt.weekday, unit="D")
    ).dt.normalize()

    df = df.sort_values("date").reset_index(drop=True)

    return df


def load_monthly_matrix(
    file_path: Path,
    code_candidates=("Номенклатура.Код", "Код"),
) -> pd.DataFrame:
    """
    Generic loader for monthly sales / inventory reports.

    Converts wide Excel structure:

        sku | янв. 2024 | февр. 2024 | ...

    into:

        sku | date | value
    """

    header_row = detect_header_row(
        file_path,
        required_words=["номенклатура", "2024"],
    )

    df = pd.read_excel(
        file_path,
        header=header_row,
        engine="openpyxl",
    )

    df.columns = [clean_column_name(column) for column in df.columns]

    code_column = None

    for candidate in code_candidates:
        if candidate in df.columns:
            code_column = candidate
            break

    if code_column is None:
        possible = [
            column
            for column in df.columns
            if "код" in column.lower()
        ]

        if possible:
            code_column = possible[0]

    if code_column is None:
        raise ValueError(
            f"SKU column was not found in {file_path.name}"
        )

    product_column = None

    for column in df.columns:
        if (
            "номенклатура" in column.lower()
            and "код" not in column.lower()
        ):
            product_column = column
            break

    id_vars = [code_column]

    if product_column:
        id_vars.append(product_column)

    month_columns = []

    for column in df.columns:
        text = column.lower()

        if re.search(r"20\d{2}", text):
            month_columns.append(column)

    if not month_columns:
        raise ValueError(
            f"No monthly columns found in {file_path.name}"
        )

    melted = df.melt(
        id_vars=id_vars,
        value_vars=month_columns,
        var_name="period",
        value_name="value",
    )

    rename = {
        code_column: "sku",
    }

    if product_column:
        rename[product_column] = "product_name"

    melted = melted.rename(columns=rename)

    melted["sku"] = melted["sku"].apply(clean_sku)

    if "product_name" in melted.columns:
        melted["product_name"] = melted["product_name"].apply(clean_text)

    melted["value"] = melted["value"].apply(parse_number)

    melted["date"] = melted["period"].apply(parse_month_period)

    melted = melted.dropna(
        subset=["sku", "date"]
    )

    melted["value"] = melted["value"].fillna(0.0)

    melted = melted.sort_values(
        ["sku", "date"]
    ).reset_index(drop=True)

    return melted


def parse_month_period(value) -> pd.Timestamp:
    """
    Converts:
        'янв. 2024'
        'сент. 2026'

    into pandas Timestamp.
    """
    text = clean_column_name(value).lower()
    text = text.replace(".", "")

    year_match = re.search(r"(20\d{2})", text)

    if not year_match:
        return pd.NaT

    year = int(year_match.group(1))

    month_number = None

    for month_name, number in MONTHS_RU.items():
        if text.startswith(month_name):
            month_number = number
            break

    if month_number is None:
        return pd.NaT

    return pd.Timestamp(
        year=year,
        month=month_number,
        day=1,
    )

# ============================================================
# MOQ / ORDER MULTIPLE LOADER
# ============================================================

def load_moq_table(
    file_path: Path,
) -> pd.DataFrame:
    """
    Load IEK supplier order-multiple table.

    Real IEK source columns:
        Код 1с
        Артикул поставщика
        Наименование
        Мин. разр. к отгр.

    Normalized output:
        sku
        moq

    'Мин. разр. к отгр.' is treated as the supplier
    order/shipment multiple.
    """

    # --------------------------------------------------------
    # 1. Detect header
    # --------------------------------------------------------

    header_row = detect_header_row(
        file_path=file_path,
        required_words=[
            "код 1с",
            "мин. разр. к отгр.",
        ],
    )

    # --------------------------------------------------------
    # 2. Read Excel
    # --------------------------------------------------------

    df = pd.read_excel(
        file_path,
        header=header_row,
        engine="openpyxl",
    )

    df.columns = [
        clean_column_name(column)
        for column in df.columns
    ]

    # --------------------------------------------------------
    # 3. Find real columns
    # --------------------------------------------------------

    sku_column = None
    moq_column = None

    for column in df.columns:

        normalized = (
            str(column)
            .strip()
            .lower()
        )

        if normalized == "код 1с":
            sku_column = column

        if (
            "мин" in normalized
            and "разр" in normalized
            and "отгр" in normalized
        ):
            moq_column = column

    if sku_column is None:
        raise ValueError(
            f"Could not find 'Код 1с' "
            f"in {file_path.name}"
        )

    if moq_column is None:
        raise ValueError(
            f"Could not find "
            f"'Мин. разр. к отгр.' "
            f"in {file_path.name}"
        )

    # --------------------------------------------------------
    # 4. Normalize
    # --------------------------------------------------------

    result = df[
        [
            sku_column,
            moq_column,
        ]
    ].copy()

    result = result.rename(
        columns={
            sku_column: "sku",
            moq_column: "moq",
        }
    )

    result["sku"] = (
        result["sku"]
        .apply(clean_sku)
    )

    result["moq"] = (
        result["moq"]
        .apply(parse_number)
    )

    # --------------------------------------------------------
    # 5. Remove invalid rows
    # --------------------------------------------------------

    result = result.dropna(
        subset=[
            "sku",
            "moq",
        ]
    ).copy()

    result = result[
        result["moq"] > 0
    ].copy()

    # --------------------------------------------------------
    # 6. One value per SKU
    # --------------------------------------------------------

    result = (
        result.drop_duplicates(
            subset=["sku"],
            keep="last",
        )
        .sort_values("sku")
        .reset_index(drop=True)
    )

    return result



def load_in_transit_table(
    file_path: Path,
) -> pd.DataFrame:
    """
    Load goods currently in transit.

    Normalized output:
        sku
        goods_in_transit

    The source Excel may contain several delivery / receipt
    columns for the same SKU.

    All valid quantities representing goods in transit are
    summed into one value per SKU.
    """

    # --------------------------------------------------------
    # 1. Find Excel header
    # --------------------------------------------------------

    possible_required_sets = [
        ["номенклатура"],
        ["код"],
        ["артикул"],
    ]

    header_row = None
    last_error = None

    for required_words in possible_required_sets:

        try:
            header_row = detect_header_row(
                file_path=file_path,
                required_words=required_words,
            )
            break

        except ValueError as error:
            last_error = error

    if header_row is None:
        raise ValueError(
            f"Could not detect header in "
            f"{file_path.name}"
        ) from last_error

    # --------------------------------------------------------
    # 2. Read Excel
    # --------------------------------------------------------

    df = pd.read_excel(
        file_path,
        header=header_row,
        engine="openpyxl",
    )

    df.columns = [
        clean_column_name(column)
        for column in df.columns
    ]

    # --------------------------------------------------------
    # 3. Find SKU column
    # --------------------------------------------------------

    sku_candidates = [
        "Номенклатура.Код",
        "Код",
        "Артикул",
    ]

    sku_column = None

    for candidate in sku_candidates:

        if candidate in df.columns:
            sku_column = candidate
            break

    if sku_column is None:

        for column in df.columns:

            column_lower = (
                str(column)
                .strip()
                .lower()
            )

            if (
                "код" in column_lower
                or "артикул" in column_lower
            ):
                sku_column = column
                break

    if sku_column is None:
        raise ValueError(
            f"Could not find SKU column "
            f"in {file_path.name}"
        )

    # --------------------------------------------------------
    # 4. Find columns containing quantities in transit
    # --------------------------------------------------------

    transit_columns = []

    for column in df.columns:

        if column == sku_column:
            continue

        column_text = (
            str(column)
            .strip()
            .lower()
        )

        # Typical names in supplier delivery files:
        #
        # Поступление
        # Поступление 25.09.2026
        # Количество к поступлению
        # В пути
        # 25.09.2026
        #
        # We try to detect these automatically.

        has_transit_word = any(
            word in column_text
            for word in [
                "поступлен",
                "в пути",
                "количество",
                "поставка",
                "приход",
            ]
        )

        has_date = bool(
            re.search(
                r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}",
                column_text,
            )
        )

        if has_transit_word or has_date:
            transit_columns.append(
                column
            )

    # --------------------------------------------------------
    # 5. Fallback
    # --------------------------------------------------------
    #
    # Sometimes Excel contains dates as actual datetime column
    # objects. clean_column_name() converts them to strings,
    # usually like:
    #
    # 2026-09-25 00:00:00
    #
    # Detect those too.
    # --------------------------------------------------------

    if not transit_columns:

        for column in df.columns:

            if column == sku_column:
                continue

            column_text = str(
                column
            ).strip()

            parsed_date = pd.to_datetime(
                column_text,
                errors="coerce",
            )

            if pd.notna(parsed_date):
                transit_columns.append(
                    column
                )

    # --------------------------------------------------------
    # 6. No transit columns found
    # --------------------------------------------------------

    if not transit_columns:

        raise ValueError(
            f"Could not find goods-in-transit "
            f"columns in {file_path.name}. "
            f"Detected columns: "
            f"{list(df.columns)}"
        )

    # --------------------------------------------------------
    # 7. Keep SKU + transit columns
    # --------------------------------------------------------

    result = df[
        [
            sku_column,
            *transit_columns,
        ]
    ].copy()

    result = result.rename(
        columns={
            sku_column: "sku",
        }
    )

    # --------------------------------------------------------
    # 8. Clean SKU
    # --------------------------------------------------------

    result["sku"] = (
        result["sku"]
        .apply(clean_sku)
    )

    # --------------------------------------------------------
    # 9. Convert all transit quantities to numeric
    # --------------------------------------------------------

    for column in transit_columns:

        result[column] = (
            result[column]
            .apply(parse_number)
            .fillna(0.0)
        )

    # --------------------------------------------------------
    # 10. Sum all active/incoming quantities
    # --------------------------------------------------------

    result["goods_in_transit"] = (
        result[
            transit_columns
        ]
        .sum(
            axis=1
        )
    )

    # --------------------------------------------------------
    # 11. Keep final normalized columns
    # --------------------------------------------------------

    result = result[
        [
            "sku",
            "goods_in_transit",
        ]
    ].copy()

    # --------------------------------------------------------
    # 12. Remove invalid rows
    # --------------------------------------------------------

    result = result.dropna(
        subset=["sku"]
    )

    result[
        "goods_in_transit"
    ] = (
        pd.to_numeric(
            result[
                "goods_in_transit"
            ],
            errors="coerce",
        )
        .fillna(0.0)
        .clip(lower=0.0)
    )

    # --------------------------------------------------------
    # 13. One final row per SKU
    # --------------------------------------------------------
    #
    # If the source contains the same SKU several times,
    # quantities are added together.
    # --------------------------------------------------------

    result = (
        result.groupby(
            "sku",
            as_index=False,
        )["goods_in_transit"]
        .sum()
        .sort_values("sku")
        .reset_index(drop=True)
    )

    return result


# ============================================================
# PROVIDED SEASONALITY LOADER
# ============================================================

def load_provided_seasonality(
    file_path: Path,
) -> pd.DataFrame:
    """
    Load externally provided seasonality coefficients.

    Expected source structure is approximately:

        Месяц
        Продажи
        Коэф. сезонности
        ...
        СЕЗОННОСТЬ

    Normalized output:

        month
        seasonal_factor

    Example:

        month    seasonal_factor
        янв      0.91
        фев      0.95
        мар      1.03
    """

    # --------------------------------------------------------
    # 1. Detect the real header
    # --------------------------------------------------------

    possible_required_sets = [
        ["месяц", "сезон"],
        ["месяц", "коэф"],
        ["месяц", "продаж"],
    ]

    header_row = None
    last_error = None

    for required_words in possible_required_sets:

        try:
            header_row = detect_header_row(
                file_path=file_path,
                required_words=required_words,
            )

            break

        except ValueError as error:
            last_error = error

    if header_row is None:
        raise ValueError(
            f"Could not detect seasonality header "
            f"in {file_path.name}"
        ) from last_error

    # --------------------------------------------------------
    # 2. Read Excel
    # --------------------------------------------------------

    df = pd.read_excel(
        file_path,
        header=header_row,
        engine="openpyxl",
    )

    df.columns = [
        clean_column_name(column)
        for column in df.columns
    ]

    # --------------------------------------------------------
    # 3. Find month column
    # --------------------------------------------------------

    month_column = None

    for column in df.columns:

        column_lower = (
            str(column)
            .strip()
            .lower()
        )

        if (
            column_lower == "месяц"
            or "месяц" in column_lower
        ):
            month_column = column
            break

    if month_column is None:
        raise ValueError(
            f"Could not find month column "
            f"in {file_path.name}"
        )

    # --------------------------------------------------------
    # 4. Find final seasonality coefficient column
    # --------------------------------------------------------

    seasonal_column = None

    # First priority:
    # exact/final "СЕЗОННОСТЬ" column.
    for column in df.columns:

        column_lower = (
            str(column)
            .strip()
            .lower()
        )

        if column_lower == "сезонность":
            seasonal_column = column
            break

    # --------------------------------------------------------
    # 5. Fallback: coefficient of seasonality
    # --------------------------------------------------------

    if seasonal_column is None:

        candidates = []

        for column in df.columns:

            column_lower = (
                str(column)
                .strip()
                .lower()
            )

            if (
                "коэф" in column_lower
                and "сезон" in column_lower
            ):
                candidates.append(column)

        if candidates:
            # If there are several yearly coefficient columns,
            # use the last one as the most recent.
            seasonal_column = candidates[-1]

    # --------------------------------------------------------
    # 6. Another fallback
    # --------------------------------------------------------

    if seasonal_column is None:

        candidates = []

        for column in df.columns:

            column_lower = (
                str(column)
                .strip()
                .lower()
            )

            if "сезон" in column_lower:
                candidates.append(column)

        if candidates:
            seasonal_column = candidates[-1]

    if seasonal_column is None:
        raise ValueError(
            f"Could not find seasonality coefficient "
            f"column in {file_path.name}. "
            f"Detected columns: {list(df.columns)}"
        )

    # --------------------------------------------------------
    # 7. Keep only necessary columns
    # --------------------------------------------------------

    result = df[
        [
            month_column,
            seasonal_column,
        ]
    ].copy()

    result = result.rename(
        columns={
            month_column: "month",
            seasonal_column: "seasonal_factor",
        }
    )

    # --------------------------------------------------------
    # 8. Clean month values
    # --------------------------------------------------------

    result["month"] = (
        result["month"]
        .apply(clean_text)
    )

    # --------------------------------------------------------
    # 9. Parse seasonality factor
    # --------------------------------------------------------

    result["seasonal_factor"] = (
        result["seasonal_factor"]
        .apply(parse_number)
    )

    # --------------------------------------------------------
    # 10. Remove invalid rows
    # --------------------------------------------------------

    result = result.dropna(
        subset=[
            "month",
            "seasonal_factor",
        ]
    ).copy()

    # Seasonal factor must be positive.
    result = result[
        result["seasonal_factor"] > 0
    ].copy()

    # --------------------------------------------------------
    # 11. Normalize Russian month names
    # --------------------------------------------------------

    result["month"] = (
        result["month"]
        .astype(str)
        .str.strip()
        .str.lower()
        .str.replace(".", "", regex=False)
    )

    # Convert common full names / variations to the short
    # format already understood by seasonality.py.
    month_aliases = {
        "январь": "янв",
        "января": "янв",
        "янв": "янв",

        "февраль": "фев",
        "февраля": "фев",
        "фев": "фев",

        "март": "мар",
        "марта": "мар",
        "мар": "мар",

        "апрель": "апр",
        "апреля": "апр",
        "апр": "апр",

        "май": "май",
        "мая": "май",

        "июнь": "июн",
        "июня": "июн",
        "июн": "июн",

        "июль": "июл",
        "июля": "июл",
        "июл": "июл",

        "август": "авг",
        "августа": "авг",
        "авг": "авг",

        "сентябрь": "сен",
        "сентября": "сен",
        "сент": "сен",
        "сен": "сен",

        "октябрь": "окт",
        "октября": "окт",
        "окт": "окт",

        "ноябрь": "ноя",
        "ноября": "ноя",
        "ноя": "ноя",

        "декабрь": "дек",
        "декабря": "дек",
        "дек": "дек",
    }

    result["month"] = (
        result["month"]
        .replace(month_aliases)
    )

    # --------------------------------------------------------
    # 12. Keep only valid months
    # --------------------------------------------------------

    valid_months = {
        "янв",
        "фев",
        "мар",
        "апр",
        "май",
        "июн",
        "июл",
        "авг",
        "сен",
        "окт",
        "ноя",
        "дек",
    }

    result = result[
        result["month"].isin(
            valid_months
        )
    ].copy()

    # --------------------------------------------------------
    # 13. Handle duplicates
    # --------------------------------------------------------
    #
    # If Excel contains several rows for the same month,
    # median is safer than blindly taking one value.
    # --------------------------------------------------------

    result = (
        result.groupby(
            "month",
            as_index=False,
        )["seasonal_factor"]
        .median()
    )

    # --------------------------------------------------------
    # 14. Sort January -> December
    # --------------------------------------------------------

    month_order = {
        "янв": 1,
        "фев": 2,
        "мар": 3,
        "апр": 4,
        "май": 5,
        "июн": 6,
        "июл": 7,
        "авг": 8,
        "сен": 9,
        "окт": 10,
        "ноя": 11,
        "дек": 12,
    }

    result["_month_order"] = (
        result["month"]
        .map(month_order)
    )

    result = (
        result.sort_values(
            "_month_order"
        )
        .drop(
            columns=[
                "_month_order"
            ]
        )
        .reset_index(drop=True)
    )

    return result

def aggregate_weekly_sales(
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """
    Aggregate transaction-level demand into weekly SKU demand.
    """

    weekly = (
        sales.groupby(
            ["sku", "week"],
            as_index=False,
        )
        .agg(
            quantity=("quantity", "sum"),
            transactions=("quantity", "size"),
            product_name=("product_name", "first"),
        )
        .sort_values(["sku", "week"])
        .reset_index(drop=True)
    )

    return weekly


def build_product_catalog(
    sales: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build basic SKU catalog from sales history.
    """

    aggregations = {
        "product_name": ("product_name", "first"),
    }

    if "unit" in sales.columns:
        aggregations["unit"] = ("unit", "first")

    catalog = (
        sales.groupby("sku", as_index=False)
        .agg(**aggregations)
        .sort_values("sku")
        .reset_index(drop=True)
    )

    return catalog


# ============================================================
# LOAD ALL DATA
# ============================================================

def load_all_core_data(
    sales_file: Path,
    monthly_sales_file: Path,
    inventory_file: Path,
    moq_file: Path | None = None,
    in_transit_file: Path | None = None,
    seasonality_file: Path | None = None,
) -> dict:
    """
    Load and normalize all procurement datasets.

    Required files:
        sales_file
        monthly_sales_file
        inventory_file

    Optional files:
        moq_file
        in_transit_file
        seasonality_file

    Returns:
        sales
        weekly_sales
        monthly_sales
        inventory
        catalog
        moq
        in_transit
        provided_seasonality
    """

    # --------------------------------------------------------
    # 1. Transaction-level sales
    # --------------------------------------------------------

    sales = load_sales_history(
        sales_file
    )

    # --------------------------------------------------------
    # 2. Monthly historical sales
    # --------------------------------------------------------

    monthly_sales = load_monthly_matrix(
        monthly_sales_file
    )

    monthly_sales = monthly_sales.rename(
        columns={
            "date": "month",
            "value": "demand",
        }
    )

    # --------------------------------------------------------
    # 3. Monthly inventory
    # --------------------------------------------------------

    inventory = load_monthly_matrix(
        inventory_file
    )

    inventory = inventory.rename(
        columns={
            "date": "month",
            "value": "stock",
        }
    )

    # --------------------------------------------------------
    # 4. Weekly transaction aggregation
    # --------------------------------------------------------

    weekly_sales = aggregate_weekly_sales(
        sales
    )

    # --------------------------------------------------------
    # 5. Product catalog
    # --------------------------------------------------------

    catalog = build_product_catalog(
        sales
    )

    # --------------------------------------------------------
    # 6. MOQ / order multiple
    # --------------------------------------------------------

    if (
        moq_file is not None
        and Path(moq_file).exists()
    ):

        moq = load_moq_table(
            Path(moq_file)
        )

    else:

        moq = pd.DataFrame(
            columns=[
                "sku",
                "moq",
            ]
        )

    # --------------------------------------------------------
    # 7. Goods in transit
    # --------------------------------------------------------

    if (
        in_transit_file is not None
        and Path(in_transit_file).exists()
    ):

        in_transit = (
            load_in_transit_table(
                Path(in_transit_file)
            )
        )

    else:

        in_transit = pd.DataFrame(
            columns=[
                "sku",
                "goods_in_transit",
            ]
        )

    # --------------------------------------------------------
    # 8. Provided seasonality
    # --------------------------------------------------------

    if (
        seasonality_file is not None
        and Path(seasonality_file).exists()
    ):

        provided_seasonality = (
            load_provided_seasonality(
                Path(seasonality_file)
            )
        )

    else:

        provided_seasonality = (
            pd.DataFrame(
                columns=[
                    "month",
                    "seasonal_factor",
                ]
            )
        )

    # --------------------------------------------------------
    # 9. Final result
    # --------------------------------------------------------

    return {
        "sales":
            sales,

        "weekly_sales":
            weekly_sales,

        "monthly_sales":
            monthly_sales,

        "inventory":
            inventory,

        "catalog":
            catalog,

        "moq":
            moq,

        "in_transit":
            in_transit,

        "provided_seasonality":
            provided_seasonality,
    }