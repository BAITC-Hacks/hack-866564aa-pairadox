import type { DashboardProduct } from "../types/dashboard";

// Product identity and history are imported from the supplied workbooks.
// ALL planning inputs below are illustrative, not live inventory or model output.
export const dashboardProducts: DashboardProduct[] = [
  {
    "sku": "300200745_",
    "name": "Atlas double socket",
    "sourceName": "К114 Роз. 2-я з/к о/у IP54 16А Atlas Profi 54 БЕЛЫЙ ATN540126 (6)",
    "supplier": "Systeme Electric",
    "kind": "socket",
    "unit": "pcs",
    "stock": 42,
    "reserved": 19,
    "incoming": 120,
    "baseForecast": 160,
    "seasonalUnits": 18,
    "growthUnits": 12,
    "correctionUnits": 8,
    "safetyStock": 10,
    "orderMultiple": 6,
    "arrivalDate": "2026-09-24",
    "priority": "high",
    "history": [
      {
        "month": "2025-09",
        "quantity": 96
      },
      {
        "month": "2025-10",
        "quantity": 70
      },
      {
        "month": "2025-11",
        "quantity": 173
      },
      {
        "month": "2025-12",
        "quantity": 77
      },
      {
        "month": "2026-01",
        "quantity": 30
      },
      {
        "month": "2026-02",
        "quantity": 78
      },
      {
        "month": "2026-03",
        "quantity": 61
      },
      {
        "month": "2026-04",
        "quantity": 87
      },
      {
        "month": "2026-05",
        "quantity": 86
      },
      {
        "month": "2026-06",
        "quantity": 50
      },
      {
        "month": "2026-07",
        "quantity": 53
      },
      {
        "month": "2026-08",
        "quantity": 101
      }
    ],
    "sourceFile": "Ежемесячные продажи в кол-м выражении SystemElectric 2024-2026.xlsx",
    "sourceSheet": "Лист_1",
    "sourceRow": 531,
    "orderRuleNote": "Order multiple from supplied Systeme Electric data."
  },
  {
    "sku": "010500008_",
    "name": "Circuit breaker 25A",
    "sourceName": "ВА47-29 (1ф) 25А IEK (12/144)",
    "supplier": "IEK",
    "kind": "breaker",
    "unit": "pcs",
    "stock": 3200,
    "reserved": 200,
    "incoming": 600,
    "baseForecast": 4500,
    "seasonalUnits": 300,
    "growthUnits": 200,
    "correctionUnits": 150,
    "safetyStock": 500,
    "orderMultiple": 12,
    "arrivalDate": "2026-09-30",
    "priority": "high",
    "history": [
      {
        "month": "2025-09",
        "quantity": 16304
      },
      {
        "month": "2025-10",
        "quantity": 17460
      },
      {
        "month": "2025-11",
        "quantity": 12410
      },
      {
        "month": "2025-12",
        "quantity": 15734
      },
      {
        "month": "2026-01",
        "quantity": 10471
      },
      {
        "month": "2026-02",
        "quantity": 7937
      },
      {
        "month": "2026-03",
        "quantity": 12663
      },
      {
        "month": "2026-04",
        "quantity": 13406
      },
      {
        "month": "2026-05",
        "quantity": 11671
      },
      {
        "month": "2026-06",
        "quantity": 15498
      },
      {
        "month": "2026-07",
        "quantity": 16790
      },
      {
        "month": "2026-08",
        "quantity": 14529
      }
    ],
    "sourceFile": "Ежемесячные продажи в количественном выражении за последние 2 года.xlsx",
    "sourceSheet": "Лист_1",
    "sourceRow": 676,
    "orderRuleNote": "Illustrative rounding rule; confirm minimum quantity, pack multiple and unit conversion with the backend."
  },
  {
    "sku": "030200193_",
    "name": "Installation box",
    "sourceName": "Установочная коробка для полых стен г/к  65х45 IMT35150 Systeme Electric (210)",
    "supplier": "Systeme Electric",
    "kind": "box",
    "unit": "pcs",
    "stock": 43000,
    "reserved": 4000,
    "incoming": 37800,
    "baseForecast": 45000,
    "seasonalUnits": 2000,
    "growthUnits": 1500,
    "correctionUnits": 800,
    "safetyStock": 5000,
    "orderMultiple": 3780,
    "arrivalDate": "2026-09-24",
    "priority": "low",
    "history": [
      {
        "month": "2025-09",
        "quantity": 15925
      },
      {
        "month": "2025-10",
        "quantity": 25149
      },
      {
        "month": "2025-11",
        "quantity": 27153
      },
      {
        "month": "2025-12",
        "quantity": 24955
      },
      {
        "month": "2026-01",
        "quantity": 18659
      },
      {
        "month": "2026-02",
        "quantity": 24170
      },
      {
        "month": "2026-03",
        "quantity": 21684
      },
      {
        "month": "2026-04",
        "quantity": 23991
      },
      {
        "month": "2026-05",
        "quantity": 24783
      },
      {
        "month": "2026-06",
        "quantity": 29064
      },
      {
        "month": "2026-07",
        "quantity": 39200
      },
      {
        "month": "2026-08",
        "quantity": 36290
      }
    ],
    "sourceFile": "Ежемесячные продажи в кол-м выражении SystemElectric 2024-2026.xlsx",
    "sourceSheet": "Лист_1",
    "sourceRow": 23,
    "orderRuleNote": "Order multiple from supplied Systeme Electric data."
  },
  {
    "sku": "200400085_",
    "name": "Shielded cable · 305m",
    "sourceName": "F/UTP (24 AWG), кат.5Е экран, 4 пары, серый  305м ITK",
    "supplier": "IEK",
    "kind": "cable",
    "unit": "m",
    "stock": 900,
    "reserved": 100,
    "incoming": 305,
    "baseForecast": 1200,
    "seasonalUnits": 100,
    "growthUnits": 80,
    "correctionUnits": 70,
    "safetyStock": 200,
    "orderMultiple": 305,
    "arrivalDate": "2026-10-10",
    "priority": "medium",
    "history": [
      {
        "month": "2025-09",
        "quantity": 5701
      },
      {
        "month": "2025-10",
        "quantity": 3675
      },
      {
        "month": "2025-11",
        "quantity": 1742
      },
      {
        "month": "2025-12",
        "quantity": 4975
      },
      {
        "month": "2026-01",
        "quantity": 1530
      },
      {
        "month": "2026-02",
        "quantity": 3000
      },
      {
        "month": "2026-03",
        "quantity": 470
      },
      {
        "month": "2026-04",
        "quantity": 1745
      },
      {
        "month": "2026-05",
        "quantity": 1155
      },
      {
        "month": "2026-06",
        "quantity": 4980
      },
      {
        "month": "2026-07",
        "quantity": 2770
      },
      {
        "month": "2026-08",
        "quantity": 1800
      }
    ],
    "sourceFile": "Ежемесячные продажи в количественном выражении за последние 2 года.xlsx",
    "sourceSheet": "Лист_1",
    "sourceRow": 3,
    "orderRuleNote": "Illustrative rounding rule; confirm minimum quantity, pack multiple and unit conversion with the backend."
  },
  {
    "sku": "300200720_",
    "name": "Atlas wall switch",
    "sourceName": "К092 Выкл 1 кл 10А с/у ATLAS ПЕСОЧНЫЙ ATN1212 (5)",
    "supplier": "Systeme Electric",
    "kind": "switch",
    "unit": "pcs",
    "stock": 3,
    "reserved": 0,
    "incoming": 80,
    "baseForecast": 90,
    "seasonalUnits": 10,
    "growthUnits": 5,
    "correctionUnits": 3,
    "safetyStock": 10,
    "orderMultiple": 5,
    "arrivalDate": "2026-09-24",
    "priority": "medium",
    "history": [
      {
        "month": "2025-09",
        "quantity": 15
      },
      {
        "month": "2025-10",
        "quantity": 41
      },
      {
        "month": "2025-11",
        "quantity": 47
      },
      {
        "month": "2025-12",
        "quantity": 41
      },
      {
        "month": "2026-01",
        "quantity": 50
      },
      {
        "month": "2026-02",
        "quantity": 25
      },
      {
        "month": "2026-03",
        "quantity": null
      },
      {
        "month": "2026-04",
        "quantity": 12
      },
      {
        "month": "2026-05",
        "quantity": null
      },
      {
        "month": "2026-06",
        "quantity": 53
      },
      {
        "month": "2026-07",
        "quantity": 25
      },
      {
        "month": "2026-08",
        "quantity": 50
      }
    ],
    "sourceFile": "Ежемесячные продажи в кол-м выражении SystemElectric 2024-2026.xlsx",
    "sourceSheet": "Лист_1",
    "sourceRow": 504,
    "orderRuleNote": "Order multiple from supplied Systeme Electric data."
  },
  {
    "sku": "081100768_",
    "name": "Emergency light · 1h",
    "sourceName": "Светильник аварийный ДПА 5030-1, NI-CD, пост.,1ч,IP20, IEK",
    "supplier": "IEK",
    "kind": "light",
    "unit": "pcs",
    "stock": 34,
    "reserved": 4,
    "incoming": 50,
    "baseForecast": 42,
    "seasonalUnits": 4,
    "growthUnits": 2,
    "correctionUnits": 2,
    "safetyStock": 12,
    "orderMultiple": 1,
    "arrivalDate": "2026-10-01",
    "priority": "low",
    "history": [
      {
        "month": "2025-09",
        "quantity": 6
      },
      {
        "month": "2025-10",
        "quantity": 14
      },
      {
        "month": "2025-11",
        "quantity": null
      },
      {
        "month": "2025-12",
        "quantity": 7
      },
      {
        "month": "2026-01",
        "quantity": 5
      },
      {
        "month": "2026-02",
        "quantity": 4
      },
      {
        "month": "2026-03",
        "quantity": null
      },
      {
        "month": "2026-04",
        "quantity": null
      },
      {
        "month": "2026-05",
        "quantity": null
      },
      {
        "month": "2026-06",
        "quantity": 4
      },
      {
        "month": "2026-07",
        "quantity": 2
      },
      {
        "month": "2026-08",
        "quantity": 7
      }
    ],
    "sourceFile": "Ежемесячные продажи в количественном выражении за последние 2 года.xlsx",
    "sourceSheet": "Лист_1",
    "sourceRow": 1903,
    "orderRuleNote": "Illustrative rounding rule; confirm minimum quantity, pack multiple and unit conversion with the backend."
  }
];
