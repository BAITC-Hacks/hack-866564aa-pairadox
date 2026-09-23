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