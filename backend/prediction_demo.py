from __future__ import annotations

from prediction import build_prediction


def main() -> None:
    rows = [
        {"purchased_at": "2026-01-10", "carbon_kg": 1.2, "water_liters": 100.0, "quantity": 1},
        {"purchased_at": "2026-01-20", "carbon_kg": 0.8, "water_liters": 90.0, "quantity": 2},
        {"purchased_at": "2026-02-05", "carbon_kg": 1.5, "water_liters": 130.0, "quantity": 1},
        {"purchased_at": "2026-02-19", "carbon_kg": 1.0, "water_liters": 95.0, "quantity": 1},
        {"purchased_at": "2026-03-14", "carbon_kg": 1.7, "water_liters": 150.0, "quantity": 1},
        {"purchased_at": "2026-04-02", "carbon_kg": 0.7, "water_liters": 80.0, "quantity": 3},
    ]
    prediction = build_prediction(rows)
    print(prediction)


if __name__ == "__main__":
    main()