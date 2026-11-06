"""Baseline 3 — transparent next-best-action rules (Task C). All outputs are PROPOSALS for human approval.

Features are computed strictly from data observable before each case's decision_at (as-of filtering).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from europress_data.sdk import open_dataset  # noqa: E402


def case_features(root, cases: pd.DataFrame, invoice_flags: pd.DataFrame | None = None) -> pd.DataFrame:
    con = open_dataset(root)
    con.register("cases", cases[["case_id", "device_id", "decision_at", "candidate_actions"]])
    f = con.sql("""
      WITH c AS (SELECT * FROM cases),
      lifts AS (SELECT c.case_id, count(*) n_lifts_56d, median(e.device_fill_pct_before) med_fill_56d,
                       avg(CASE WHEN e.trigger_type='AD_HOC_CUSTOMER' THEN 1 ELSE 0 END) adhoc_share_56d,
                       avg(CASE WHEN e.driver_reported_side_waste THEN 1 ELSE 0 END) side_share_56d
                FROM c JOIN collection_events e ON e.device_id=c.device_id AND e.actual_at < c.decision_at
                     AND e.actual_at >= c.decision_at - INTERVAL 56 DAY AND e.status IN ('COMPLETED','PARTIAL') GROUP BY 1),
      skips AS (SELECT c.case_id, count(*) n_skips_56d FROM c JOIN collection_events e ON e.device_id=c.device_id
                AND e.scheduled_at < c.decision_at AND e.scheduled_at >= c.decision_at - INTERVAL 56 DAY AND e.status='SKIPPED_LOW_FILL' GROUP BY 1),
      recon AS (SELECT c.case_id,   -- recomputed as-of: only tickets published before the decision (not the extraction-time status column)
                       avg(CASE WHEN abs(e.device_estimated_collected_kg - w.allocated_net_kg) > 0.10 * w.allocated_net_kg THEN 1.0 ELSE 0 END) wb_diff_share_90d,
                       count(*) n_recon_90d
                FROM c JOIN collection_events e ON e.device_id=c.device_id AND e.actual_at < c.decision_at
                     AND e.actual_at >= c.decision_at - INTERVAL 90 DAY AND e.device_estimated_collected_kg IS NOT NULL
                JOIN weighbridge_tickets w ON w.operator_job_ref = e.operator_job_ref AND w.published_at < c.decision_at AND w.allocated_net_kg > 0
                GROUP BY 1),
      fullh AS (SELECT c.case_id, count(*) full_hours_28d FROM c JOIN telemetry_dedup t ON t.device_id=c.device_id
                AND t.received_at < c.decision_at AND t.measured_at >= c.decision_at - INTERVAL 28 DAY AND t.operational_state='FULL' GROUP BY 1),
      sens AS (SELECT c.case_id, avg(CASE WHEN t.quality_flag IN ('SENSOR_FAULT','LOW_CONFIDENCE') THEN 1.0 ELSE 0 END) bad_mass_share_14d
               FROM c JOIN telemetry_dedup t ON t.device_id=c.device_id AND t.received_at < c.decision_at
               AND t.measured_at >= c.decision_at - INTERVAL 14 DAY GROUP BY 1),
      qual AS (SELECT c.case_id, sum(CASE WHEN q.grade IN ('C','R') THEN 1 ELSE 0 END) n_grade_cr_90d, count(*) n_graded_90d
               FROM c JOIN collection_events e ON e.device_id=c.device_id JOIN weighbridge_tickets w ON w.operator_job_ref=e.operator_job_ref
               JOIN quality_assessments q ON q.ticket_id=w.ticket_id AND q.published_at < c.decision_at
               AND q.published_at >= c.decision_at - INTERVAL 90 DAY GROUP BY 1)
      SELECT c.*, d.collection_policy, d.fixed_schedule_per_week, d.on_call_threshold_pct, d.has_weight_measurement,
             d.material_stream, d.container_volume_m3, m.credit_eligible, m.max_days_between_collections, d.contract_id,
             l.* EXCLUDE (case_id), s.n_skips_56d, r.wb_diff_share_90d, r.n_recon_90d, f.full_hours_28d, se.bad_mass_share_14d,
             q.n_grade_cr_90d, q.n_graded_90d
      FROM c JOIN devices d USING (device_id) JOIN material_classes m USING (material_stream)
      LEFT JOIN lifts l USING (case_id) LEFT JOIN skips s USING (case_id) LEFT JOIN recon r USING (case_id)
      LEFT JOIN fullh f USING (case_id) LEFT JOIN sens se USING (case_id) LEFT JOIN qual q USING (case_id)""").df()
    con.close()
    for col in ("n_lifts_56d", "n_skips_56d", "full_hours_28d", "n_grade_cr_90d", "n_graded_90d", "n_recon_90d"):
        f[col] = f[col].fillna(0)
    f["invoice_flags_90d"] = 0
    if invoice_flags is not None and len(invoice_flags):
        flags = invoice_flags.copy()
        flags["contract_id"] = "CTR-" + flags.entity_id.str[4:9]
        for i, r in f.iterrows():
            g = flags[(flags.contract_id == r.contract_id) & (flags.issued_at < r.decision_at) &
                      (flags.issued_at >= r.decision_at - pd.Timedelta(days=90))]
            f.at[i, "invoice_flags_90d"] = len(g)
    return f


def decide(f: pd.DataFrame) -> pd.DataFrame:
    out = []
    for r in f.itertuples():
        cands = set(r.candidate_actions.split(","))
        a = "NO_ACTION"
        mf = r.med_fill_56d if pd.notna(r.med_fill_56d) else 60
        if r.collection_policy in ("FIXED_SCHEDULE", "HYBRID"):
            if mf < 45 and "REDUCE_FREQUENCY" in cands:
                a = "REDUCE_FREQUENCY"
            elif mf < 55 and "SWITCH_TO_ON_CALL" in cands:
                a = "SWITCH_TO_ON_CALL"
            elif r.full_hours_28d > 24 and "INCREASE_FREQUENCY" in cands:
                a = "INCREASE_FREQUENCY"
        else:
            if r.full_hours_28d > 24 and "LOWER_THRESHOLD" in cands:
                a = "LOWER_THRESHOLD"
            elif mf < 75 and "RAISE_THRESHOLD" in cands:
                a = "RAISE_THRESHOLD"
        if a == "NO_ACTION" and r.credit_eligible and r.n_grade_cr_90d >= 2 and "SORTING_INTERVENTION" in cands:
            a = "SORTING_INTERVENTION"
        verify = bool((r.n_recon_90d >= 3 and (r.wb_diff_share_90d or 0) > 0.3) or (r.bad_mass_share_14d or 0) > 0.2)
        out.append({"case_id": r.case_id, "action": a, "verify_weight_sensor": verify, "review_invoices": bool(r.invoice_flags_90d > 0),
                    "rationale": f"median fill before lift (56 d) = {mf:.0f} %, full hours (28 d) = {int(r.full_hours_28d)}; proposal requires human approval"})
    return pd.DataFrame(out)
