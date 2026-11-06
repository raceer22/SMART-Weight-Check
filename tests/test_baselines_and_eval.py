import pandas as pd

from b1_economic_calculator import compute
from b2_rules_anomaly import run as run_rules
from europress_data.evaluate import score_a, score_b


def test_b1_reconstructs_charges_where_mass_is_observable(small_dataset):
    pred, _ = compute(small_dataset / "public")
    s = score_a(pred, small_dataset / "public" / "labels_dev", "validation")
    assert s["n_reference_events"] > 0
    assert s["processing_cost_eur:exact_to_cent_share"] > 0.9
    assert s["per_t:fabricated_where_reference_null"] == 0


def test_rules_baseline_scores(small_dataset):
    pred, _, _ = run_rules(small_dataset / "public")
    s = score_b(pred, small_dataset / "public" / "labels_dev", "validation")
    assert 0 <= s["macro_f1"] <= 1
