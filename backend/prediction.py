from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from math import sqrt


@dataclass
class LinearModel:
    slope: float
    intercept: float

    def predict(self, x_value: float) -> float:
        return self.intercept + (self.slope * x_value)


def _month_labels(rows: list[Any]) -> list[str]:
    labels = sorted({row["purchased_at"][:7] for row in rows})
    return labels


def _monthly_totals(rows: list[Any]) -> list[dict[str, float]]:
    labels = _month_labels(rows)
    totals: dict[str, dict[str, float]] = {
        label: {"co2": 0.0, "water": 0.0} for label in labels
    }

    for row in rows:
        label = row["purchased_at"][:7]
        totals[label]["co2"] += row["carbon_kg"] * row["quantity"]
        totals[label]["water"] += row["water_liters"] * row["quantity"]

    return [
        {"month": label, "co2": values["co2"], "water": values["water"]}
        for label, values in totals.items()
    ]


def _fit_linear_model(xs: list[float], ys: list[float], weights: list[float] | None = None) -> LinearModel:
    """Fit a (optionally) weighted linear regression using closed-form solution.

    If weights is None, ordinary least squares is used. When weights provided,
    more recent observations can be given higher weight to make forecasts
    respond faster to changes.
    """
    n = len(xs)
    if n == 0:
        return LinearModel(0.0, 0.0)

    if weights is None:
        weights = [1.0] * n

    sw = sum(weights)
    mean_x = sum(w * x for w, x in zip(weights, xs)) / sw
    mean_y = sum(w * y for w, y in zip(weights, ys)) / sw

    var_x = sum(w * (x - mean_x) ** 2 for w, x in zip(weights, xs))
    if var_x == 0:
        return LinearModel(0.0, mean_y)

    cov_xy = sum(w * (x - mean_x) * (y - mean_y) for w, x, y in zip(weights, xs, ys))
    slope = cov_xy / var_x
    intercept = mean_y - (slope * mean_x)
    return LinearModel(slope, intercept)


def _mean_absolute_error(actuals: list[float], predictions: list[float]) -> float:
    if not actuals:
        return 0.0
    return sum(abs(actual - predicted) for actual, predicted in zip(actuals, predictions)) / len(actuals)


def _rmse(actuals: list[float], predictions: list[float], weights: list[float] | None = None) -> float:
    if not actuals:
        return 0.0
    if weights is None:
        weights = [1.0] * len(actuals)
    sw = sum(weights)
    mse = sum(w * (a - p) ** 2 for a, p, w in zip(actuals, predictions, weights)) / sw
    return sqrt(mse)


def _future_month_label(base_label: str, offset: int) -> str:
    year, month = map(int, base_label.split("-"))
    total_months = (year * 12) + (month - 1) + offset
    future_year = total_months // 12
    future_month = (total_months % 12) + 1
    return f"{future_year:04d}-{future_month:02d}"


def build_prediction(rows: list[Any]) -> dict[str, Any]:
    monthly_history = _monthly_totals(rows)
    if not monthly_history:
        return {
            "model_type": "linear_regression",
            "trained_months": 0,
            "next_month": {"co2": 0.0, "water": 0.0},
            "quarter_projection": [],
            "metrics": {"co2_mae": 0.0, "water_mae": 0.0},
            "insight": "Add a few purchases to generate your sustainability forecast.",
        }

    # Use the chronological order of monthly_history (oldest -> newest)
    xs = list(range(len(monthly_history)))
    co2_values = [point["co2"] for point in monthly_history]
    water_values = [point["water"] for point in monthly_history]

    # Favor recent months with exponential weights so predictions adapt faster
    # decay_rate controls how quickly older months lose influence (0.0 = no decay)
    decay_rate = 0.3
    weights = [pow(1.0 - decay_rate, (len(xs) - 1 - i)) for i in range(len(xs))]

    # Train on all months but use weighted fit for robustness; compute a simple
    # backtest MAE by leaving the last month out when possible.
    if len(monthly_history) >= 3:
        train_xs = xs[:-1]
        train_co2 = co2_values[:-1]
        train_water = water_values[:-1]
        train_weights = weights[:-1]

        co2_model = _fit_linear_model(train_xs, train_co2, train_weights)
        water_model = _fit_linear_model(train_xs, train_water, train_weights)

        # backtest prediction for last observed month
        test_x = xs[-1]
        co2_pred_test = co2_model.predict(test_x)
        water_pred_test = water_model.predict(test_x)
        test_metrics = {
            "co2_mae": round(_mean_absolute_error([co2_values[-1]], [co2_pred_test]), 2),
            "water_mae": round(_mean_absolute_error([water_values[-1]], [water_pred_test]), 2),
        }

        # Final model fit on full history (weights help recent months influence)
        co2_model = _fit_linear_model(xs, co2_values, weights)
        water_model = _fit_linear_model(xs, water_values, weights)
    else:
        co2_model = _fit_linear_model(xs, co2_values, weights)
        water_model = _fit_linear_model(xs, water_values, weights)
        test_metrics = {"co2_mae": 0.0, "water_mae": 0.0}

    last_index = xs[-1]
    last_month = monthly_history[-1]["month"]

    # Build projections and compute simple RMSE-based intervals
    projection = []
    # compute in-sample RMSE to estimate uncertainty
    co2_preds_in_sample = [co2_model.predict(x) for x in xs]
    water_preds_in_sample = [water_model.predict(x) for x in xs]
    co2_rmse = _rmse(co2_values, co2_preds_in_sample, weights)
    water_rmse = _rmse(water_values, water_preds_in_sample, weights)
    z = 1.96  # approx 95% CI

    for offset in range(1, 4):
        x_value = last_index + offset
        co2_pred = max(0.0, co2_model.predict(x_value))
        water_pred = max(0.0, water_model.predict(x_value))
        co2_margin = round(z * co2_rmse, 2)
        water_margin = round(z * water_rmse, 2)
        projection.append(
            {
                "month": _future_month_label(last_month, offset),
                "co2": round(co2_pred, 2),
                "co2_ci": [round(max(0.0, co2_pred - co2_margin), 2), round(co2_pred + co2_margin, 2)],
                "water": round(water_pred, 2),
                "water_ci": [round(max(0.0, water_pred - water_margin), 2), round(water_pred + water_margin, 2)],
            }
        )

    next_month = projection[0]

    # Friendly insight + human-readable summary
    last_co2 = monthly_history[-1]["co2"]
    last_water = monthly_history[-1]["water"]
    def pct_change(next_val: float, last_val: float) -> float:
        if last_val == 0:
            return float('inf') if next_val > 0 else 0.0
        return round(((next_val - last_val) / abs(last_val)) * 100.0, 1)

    co2_change_pct = pct_change(next_month["co2"], last_co2)
    water_change_pct = pct_change(next_month["water"], last_water)

    co2_margin_val = round(z * co2_rmse, 2)
    water_margin_val = round(z * water_rmse, 2)

    def confidence_level(margin: float, pred: float) -> str:
        if pred <= 0:
            return "Low"
        ratio = margin / pred
        if ratio < 0.10:
            return "High"
        if ratio < 0.25:
            return "Medium"
        return "Low"

    co2_conf = confidence_level(co2_margin_val, next_month["co2"])
    water_conf = confidence_level(water_margin_val, next_month["water"])

    simple_summary = (
        f"Next month we expect ~{next_month['co2']} kg CO2 ({'+' if co2_change_pct>=0 else ''}{co2_change_pct}% vs last month)"
        f" and ~{next_month['water']} L water ({'+' if water_change_pct>=0 else ''}{water_change_pct}% vs last month)."
    )

    quick_tips = [
        "Prefer seasonal or local produce to cut food-related CO2.",
        "Choose reusable or concentrated home products to lower water use.",
        "Batch errands and deliveries to reduce repeated transport impact.",
    ]

    friendly = {
        "summary": simple_summary,
        "co2": {
            "next_month": next_month["co2"],
            "change_pct": co2_change_pct,
            "margin": co2_margin_val,
            "confidence": co2_conf,
            "note": f"A {co2_conf} confidence interval of ±{co2_margin_val} kg",
        },
        "water": {
            "next_month": next_month["water"],
            "change_pct": water_change_pct,
            "margin": water_margin_val,
            "confidence": water_conf,
            "note": f"A {water_conf} confidence interval of ±{water_margin_val} L",
        },
        "quick_tips": quick_tips,
    }

    insight = (
        f"Based on your last {len(monthly_history)} months, your impact looks "
        f"{'higher' if (co2_model.slope>0 or water_model.slope>0) else 'lower'} than before. "
        f"{simple_summary} Try a quick tip: {quick_tips[0]}"
    )

    return {
        "model_type": "linear_regression",
        "trained_months": len(monthly_history),
        "next_month": {"co2": next_month["co2"], "water": next_month["water"]},
        "quarter_projection": projection,
        "metrics": test_metrics,
        "coefficients": {
            "co2_slope": round(co2_model.slope, 4),
            "co2_intercept": round(co2_model.intercept, 4),
            "water_slope": round(water_model.slope, 4),
            "water_intercept": round(water_model.intercept, 4),
        },
        "insight": insight,
        "friendly": friendly,
    }
