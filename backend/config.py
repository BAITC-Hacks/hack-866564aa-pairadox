from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
IEK_DIR = DATA_DIR / "IEK"


SALES_HISTORY_FILE = IEK_DIR / "Динамика продаж_2025-2026.xlsx"

MONTHLY_SALES_FILE = (
    IEK_DIR
    / "Ежемесячные продажи в количественном выражении за последние 2 года.xlsx"
)

INVENTORY_FILE = (
    IEK_DIR
    / "Ежемесячные остатки продукции за последние 2 года  ИЭК.xlsx"
)

MOQ_FILE = IEK_DIR / "MOQ  ИЭК.xlsx"

IN_TRANSIT_FILE = IEK_DIR / "Путь ИЭК 22.09.2026.xlsx"

SEASONALITY_FILE = IEK_DIR / "Сезонность ИЭК.xlsx"

# ============================================================
# PROCUREMENT SETTINGS
# ============================================================

# Temporary assumption until real supplier lead time
# is provided.
DEFAULT_LEAD_TIME_MONTHS = 1.0

# Target service level used for safety stock.
DEFAULT_SERVICE_LEVEL = 0.95

# Number of future months to forecast.
DEFAULT_MONTHS_AHEAD = 3


# ============================================================
# ANOMALY SETTINGS
# ============================================================

# Supported:
# "median"
# "zero"
DEFAULT_ANOMALY_REPLACEMENT_STRATEGY = "median"


# ============================================================
# PIPELINE MODULE DEFAULTS
# ============================================================

DEFAULT_APPLY_ANOMALY_EXCLUSION = True

DEFAULT_APPLY_STOCKOUT_CORRECTION = True

DEFAULT_APPLY_SEASONALITY = True

DEFAULT_APPLY_GROWTH_TREND = True