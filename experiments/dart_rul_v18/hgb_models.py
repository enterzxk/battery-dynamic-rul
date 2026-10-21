"""Cell-isolated strong HGB baselines for DART-RUL V18."""
from __future__ import annotations

import io
import json
import math
import os
from pathlib import Path

import numpy as np

MAX_ITER = 150
MAX_LEAF_NODES = 15
L2_REGULARIZATION = 1.0


def _finite_matrix(examples, key):
    x = np.stack([np.asarray(e[key], dtype=float) for e in examples])
    if x.ndim != 2 or not np.isfinite(x).all():
        raise ValueError("nonfinite or malformed " + key)
    return x


def _cell_weights(examples):
    from data_protocol import weight_cells
    w = weight_cells(examples)
    if not np.isfinite(w).all() or (w <= 0).any():
        raise ValueError("invalid cell-equal weights")
    return w


def _two_cell_folds(examples, seed):
    ids = sorted({str(e["cell_id"]) for e in examples})
    if len(ids) < 2:
        raise ValueError("cell-isolated OOF requires at least two cells")
    rng = np.random.RandomState(seed)
    rng.shuffle(ids)
    folds = [set(ids[::2]), set(ids[1::2])]
    if any(not fold for fold in folds):
        raise ValueError("empty cell-isolated OOF fold")
    return folds


def _new_regressor(seed):
    from sklearn.ensemble import HistGradientBoostingRegressor
    return HistGradientBoostingRegressor(
        max_iter=MAX_ITER, max_leaf_nodes=MAX_LEAF_NODES,
        l2_regularization=L2_REGULARIZATION, random_state=int(seed))


def _new_classifier(seed):
    from sklearn.ensemble import HistGradientBoostingClassifier
    return HistGradientBoostingClassifier(
        max_iter=MAX_ITER, max_leaf_nodes=MAX_LEAF_NODES,
        l2_regularization=L2_REGULARIZATION, random_state=int(seed))


def _fit(model, x, y, w, name, on_fit):
    if len(x) == 0 or len(y) != len(x) or len(w) != len(x):
        raise ValueError("empty or mismatched fit data for " + name)
    if not np.isfinite(x).all() or not np.isfinite(y).all() or not np.isfinite(w).all():
        raise ValueError("nonfinite fit data for " + name)
    if on_fit is not None:
        on_fit("start", name)
    model.fit(x, y, sample_weight=w)
    if on_fit is not None:
        on_fit("complete", name)
    return model


def _cell_equal_residual_weights(examples):
    counts = {}
    for e in examples:
        counts[e["cell_id"]] = counts.get(e["cell_id"], 0) + 1
    if not counts:
        raise ValueError("empty OOF residual set")
    w = np.asarray([1.0 / counts[e["cell_id"]] for e in examples], dtype=float)
    if not np.isfinite(w).all() or (w <= 0).any():
        raise ValueError("invalid OOF residual weights")
    return w / w.sum()


def _create_only_joblib(path, obj):
    import joblib
    path = Path(path)
    payload = io.BytesIO()
    joblib.dump(obj, payload)
    fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload.getvalue())
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise


class EmpiricalRUL:
    def __init__(self, values, weights=None):
        values = np.asarray(values, dtype=float)
        if values.ndim != 1 or len(values) == 0 or not np.isfinite(values).all() or (values < 0).any():
            raise ValueError("invalid empirical RUL support")
        order = np.argsort(values, kind="mergesort")
        self.values = values[order]
        w = np.ones(len(values), dtype=float) if weights is None else np.asarray(weights, dtype=float)[order]
        if w.shape != values.shape or not np.isfinite(w).all() or (w < 0).any() or w.sum() <= 0:
            raise ValueError("invalid empirical RUL weights")
        self.weights = w / w.sum()
        self.cumulative = np.cumsum(self.weights)
        self.cumulative[-1] = 1.0

    def cdf(self, x):
        a = np.asarray(x, dtype=float)
        idx = np.searchsorted(self.values, a, side="right") - 1
        idx = np.clip(idx, 0, len(self.values) - 1)
        result = np.where(a < self.values[0], 0.0, self.cumulative[idx])
        result = np.where(a < 0.0, 0.0, result)
        return float(result) if np.ndim(result) == 0 else result

    def mean(self):
        return float(np.dot(self.values, self.weights))

    def quantile(self, p):
        p = float(p)
        if not 0.0 <= p <= 1.0:
            raise ValueError("quantile probability outside [0,1]")
        return float(self.values[min(len(self.values) - 1,
                                     int(np.searchsorted(self.cumulative, p, side="left")))])


class HGBFullWindow:
    def __init__(self, model, residuals, residual_weights):
        self.model = model
        self.residuals = np.asarray(residuals, dtype=float)
        self.residual_weights = np.asarray(residual_weights, dtype=float)

    def predict(self, example):
        mu = float(self.model.predict(np.asarray(example["x_query"], dtype=float)[None, :])[0])
        eol_duration = np.exp(mu + self.residuals)
        shifted = np.maximum(0.0, eol_duration - float(example["elapsed_from_warmup_weeks"]))
        return EmpiricalRUL(shifted, self.residual_weights)


class HGBHurdle:
    def __init__(self, classifier, regressor, residuals, residual_weights):
        self.classifier = classifier
        self.regressor = regressor
        self.residuals = np.asarray(residuals, dtype=float)
        self.residual_weights = np.asarray(residual_weights, dtype=float)

    def predict(self, example):
        x = np.asarray(example["x_query"], dtype=float)[None, :]
        classes = np.asarray(self.classifier.classes_)
        one = np.flatnonzero(classes == 1)
        if len(one) != 1:
            raise ValueError("hurdle classifier has no event class 1")
        p = float(self.classifier.predict_proba(x)[0, one[0]])
        if not math.isfinite(p) or not 0.0 <= p <= 1.0:
            raise ValueError("invalid hurdle probability")
        mu = float(self.regressor.predict(x)[0])
        positives = np.exp(mu + self.residuals)
        return HurdleRUL(p, positives, self.residual_weights)


class HurdleRUL:
    def __init__(self, zero_mass, positive_values, positive_weights):
        self.zero_mass = float(zero_mass)
        if not 0.0 <= self.zero_mass <= 1.0:
            raise ValueError("invalid zero atom")
        self.positive = EmpiricalRUL(positive_values, positive_weights)
        if (self.positive.values <= 0).any():
            raise ValueError("positive hurdle component must be strictly positive")

    def cdf(self, x):
        a = np.asarray(x, dtype=float)
        if np.any(a < 0.0):
            raise ValueError("negative RUL CDF query")
        result = self.zero_mass + (1.0 - self.zero_mass) * self.positive.cdf(a)
        return float(result) if np.ndim(result) == 0 else result

    def mean(self):
        return float((1.0 - self.zero_mass) * self.positive.mean())

    def quantile(self, p):
        p = float(p)
        if not 0.0 <= p <= 1.0:
            raise ValueError("quantile probability outside [0,1]")
        if p <= self.zero_mass or self.zero_mass >= 1.0:
            return 0.0
        return self.positive.quantile((p - self.zero_mass) / (1.0 - self.zero_mass))


def train_models(train, seed, output_dir, on_fit=None):
    """Train exact-budget A/B HGB models; output_dir must be a fresh directory."""
    from data_protocol import weight_cells

    if not train:
        raise ValueError("empty training examples")
    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        raise ValueError("output_dir must already exist and be fresh")
    if any(e.get("role") != "train" for e in train):
        raise ValueError("train_models accepts train role only")
    if any(not np.isfinite(np.asarray(e["x_query"], dtype=float)).all() for e in train):
        raise ValueError("nonfinite training feature")
    known = [e for e in train if e["event_time_epoch"] is not None]
    if not known:
        raise ValueError("no known-event rows for full-window HGB")
    if any(e["delta_weeks"] < 0 for e in known):
        raise ValueError("negative query delta")
    # Anchor epoch is recoverable from the fixed query contract; it is label-side only.
    full_y = np.asarray([
        math.log((float(e["event_time_epoch"]) -
                  (float(e["query_epoch"]) - float(e["elapsed_from_warmup_weeks"]) * 604800.0)) / 604800.0)
        for e in known
    ], dtype=float)
    if not np.isfinite(full_y).all():
        raise ValueError("nonfinite full-window log duration")
    folds = _two_cell_folds(known, seed)
    residuals, residual_examples = [], []
    for fold_i, held in enumerate(folds):
        fit_rows = [e for e in known if e["cell_id"] not in held]
        val_rows = [e for e in known if e["cell_id"] in held]
        if not fit_rows or not val_rows:
            raise ValueError("empty full-window OOF cell fold")
        train_x = _finite_matrix(fit_rows, "x_query")
        val_x = _finite_matrix(val_rows, "x_query")
        y = np.asarray([
            math.log((float(e["event_time_epoch"]) -
                      (float(e["query_epoch"]) - float(e["elapsed_from_warmup_weeks"]) * 604800.0)) / 604800.0)
            for e in fit_rows
        ], dtype=float)
        val_y = np.asarray([
            math.log((float(e["event_time_epoch"]) -
                      (float(e["query_epoch"]) - float(e["elapsed_from_warmup_weeks"]) * 604800.0)) / 604800.0)
            for e in val_rows
        ], dtype=float)
        model = _fit(_new_regressor(seed), train_x, y, _cell_weights(fit_rows),
                     "hgb_fullwindow_oof_" + str(fold_i + 1), on_fit)
        residuals.extend((val_y - model.predict(val_x)).tolist())
        residual_examples.extend(val_rows)
    full_model = _fit(_new_regressor(seed), _finite_matrix(known, "x_query"), full_y,
                      _cell_weights(known), "hgb_fullwindow_full", on_fit)
    full_residual_weights = _cell_equal_residual_weights(residual_examples)
    full_fit_weights = _cell_weights(known)
    full_predictor = HGBFullWindow(full_model, np.asarray(residuals), full_residual_weights)
    _create_only_joblib(output_dir / "hgb_fullwindow_full.joblib", full_model)
    _create_only_joblib(output_dir / "hgb_fullwindow_distribution.joblib", {
        "residuals": np.asarray(residuals), "residual_weights": full_residual_weights,
        "full_fit_weights": full_fit_weights})

    labels = np.asarray([int(e["y_event"]) for e in train], dtype=int)
    if set(labels.tolist()) != {0, 1}:
        raise ValueError("hurdle classifier requires both event labels")
    classifier_fit_weights = _cell_weights(train)
    classifier = _fit(_new_classifier(seed), _finite_matrix(train, "x_query"), labels,
                      classifier_fit_weights, "hgb_hurdle_classifier_full", on_fit)
    if set(np.asarray(classifier.classes_).tolist()) != {0, 1}:
        raise ValueError("hurdle classifier classes are incomplete")

    positive = [e for e in train if e["event_time_epoch"] is not None and
                e["target_rul_weeks"] is not None and float(e["target_rul_weeks"]) > 0.0]
    if not positive:
        raise ValueError("no positive known-event RUL rows for hurdle regressor")
    positive_ids = {e["cell_id"] for e in positive}
    reg_folds = _two_cell_folds([e for e in train if e["cell_id"] in positive_ids], seed)
    reg_residuals, reg_residual_examples = [], []
    for fold_i, held in enumerate(reg_folds):
        fit_rows = [e for e in positive if e["cell_id"] not in held]
        val_rows = [e for e in positive if e["cell_id"] in held]
        if not fit_rows or not val_rows:
            raise ValueError("empty positive-RUL OOF cell fold")
        fit_y = np.log(np.asarray([float(e["target_rul_weeks"]) for e in fit_rows], dtype=float))
        val_y = np.log(np.asarray([float(e["target_rul_weeks"]) for e in val_rows], dtype=float))
        model = _fit(_new_regressor(seed), _finite_matrix(fit_rows, "x_query"), fit_y,
                     _cell_weights(fit_rows), "hgb_hurdle_positive_oof_" + str(fold_i + 1), on_fit)
        reg_residuals.extend((val_y - model.predict(_finite_matrix(val_rows, "x_query"))).tolist())
        reg_residual_examples.extend(val_rows)
    positive_fit_weights = _cell_weights(positive)
    full_regressor = _fit(
        _new_regressor(seed), _finite_matrix(positive, "x_query"),
        np.log(np.asarray([float(e["target_rul_weeks"]) for e in positive], dtype=float)),
        positive_fit_weights, "hgb_hurdle_positive_full", on_fit)
    reg_residual_weights = _cell_equal_residual_weights(reg_residual_examples)
    hurdle_predictor = HGBHurdle(classifier, full_regressor, reg_residuals,
                                 reg_residual_weights)
    _create_only_joblib(output_dir / "hgb_hurdle_classifier_full.joblib", classifier)
    _create_only_joblib(output_dir / "hgb_hurdle_positive_full.joblib", full_regressor)
    _create_only_joblib(output_dir / "hgb_hurdle_distribution.joblib", {
        "residuals": np.asarray(reg_residuals), "residual_weights": reg_residual_weights,
        "classifier_fit_weights": classifier_fit_weights,
        "positive_regressor_fit_weights": positive_fit_weights,
        "classifier_full_probability_is_in_sample": True})
    return {"hgb_fullwindow": full_predictor, "hgb_hurdle": hurdle_predictor}
