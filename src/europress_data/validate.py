"""Dataset validator. python -m europress_data.validate --profile competition

Produces reports/<profile>/validation_report.json and validation_summary.md.
Checks are 'blocking' (must be zero violations for release) or 'warning' (plausibility).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import duckdb

from .config import ROOT
from .export import sha256_file
from .schema import TABLES

PII_PATTERNS = {
    "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "phone": r"(^|[ ,;:(])(\+358 ?|0)[0-9]{1,2}[ -][0-9]{3}[ -]?[0-9]{3,4}($|[ ,;:)])",
    "fi_personal_id": r"\b\d{6}[-+A]\d{3}[0-9A-Y]\b",
    "iban": r"\bFI\d{2}[ ]?\d{4}",
}


class V:
    def __init__(self, data_dir: Path):
        self.d = Path(data_dir)
        self.pub = self.d / "public"
        self.priv = self.d / "private_evaluation"
        self.con = duckdb.connect()
        self.con.execute("SET memory_limit='2500MB'; SET threads=2; SET preserve_insertion_order=false; SET TimeZone='UTC'")
        self.results = []
        self.views = {}
        self._register()

    def _register(self):
        for pkg, root in (("pub", self.pub), ("priv", self.priv), ("hold", self.priv / "holdout_full")):
            if not root.exists():
                continue
            for key, t in TABLES.items():
                if pkg == "hold" and t["pkg"] != "public":
                    continue
                if pkg == "priv" and t["pkg"] != "private":
                    continue
                if pkg == "pub" and t["pkg"] != "public":
                    continue
                if t.get("partitioned"):
                    g = root / key / "*" / "*.parquet"
                    if not list((root / key).glob("*/*.parquet")) if (root / key).exists() else True:
                        continue
                else:
                    g = root / f"{key}.parquet"
                    if not g.exists():
                        continue
                name = f"{pkg}_{key.replace('/', '_')}"
                self.con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{g}', hive_partitioning=false)")
                self.views[(pkg, key)] = name

    def v(self, key, pkg="pub"):
        return self.views.get((pkg, key))

    def q(self, sql):
        return self.con.execute(sql).fetchone()[0]

    def check(self, cid, desc, level, n_viol, detail=None, scenario=None):
        self.results.append({"check_id": cid, "description": desc, "level": level, "violations": int(n_viol or 0),
                             "passed": int(n_viol or 0) == 0, "detail": detail})

    # ------------------------------------------------------------------ structural
    def structural(self):
        for (pkg, key), name in self.views.items():
            t = TABLES[key]
            if t["pk"]:
                pk = ", ".join(t["pk"])
                n = self.q(f"SELECT count(*) FROM (SELECT {pk}, count(*) c FROM {name} GROUP BY {pk} HAVING c > 1)")
                self.check(f"PK:{pkg}:{key}", f"primary key unique ({pk})", "blocking", n)
            for c in t["cols"]:
                if not c["nullable"]:
                    n = self.q(f"SELECT count(*) FROM {name} WHERE {c['name']} IS NULL")
                    if n:
                        self.check(f"NOTNULL:{pkg}:{key}.{c['name']}", "non-nullable column has NULLs", "blocking", n)
                if c["values"] and "|" in c["values"]:
                    vals = ", ".join(f"'{x}'" for x in c["values"].split("|"))
                    n = self.q(f"SELECT count(*) FROM {name} WHERE {c['name']} IS NOT NULL AND CAST({c['name']} AS VARCHAR) NOT IN ({vals})")
                    if n:
                        self.check(f"ENUM:{pkg}:{key}.{c['name']}", "value outside documented domain", "blocking", n)
            for col, ref in t["fk"].items():
                rkey, rcol = ref.rsplit(".", 1)
                rname = self.views.get((pkg, rkey))
                if rname is None:
                    continue
                n = self.q(f"SELECT count(*) FROM {name} a WHERE a.{col} IS NOT NULL AND a.{col} NOT IN (SELECT {rcol} FROM {rname})")
                self.check(f"FK:{pkg}:{key}.{col}", f"foreign key -> {ref}", "blocking", n)
        self.check("STRUCT:all_columns_documented", "every published column documented (enforced at write)", "blocking", 0)

    # ------------------------------------------------------------------ temporal / semantic
    def semantic(self):
        te, ce = self.v("telemetry/telemetry_hourly"), self.v("operations/collection_events")
        dv, cv = self.v("reference/devices"), self.v("reference/contract_versions")
        if te:
            self.check("TIME:telemetry_received_after_measured", "received_at >= measured_at", "blocking",
                       self.q(f"SELECT count(*) FROM {te} WHERE received_at < measured_at"))
            self.check("UNIT:fill_pct_range", "fill_pct in [0,100]", "blocking", self.q(f"SELECT count(*) FROM {te} WHERE fill_pct < 0 OR fill_pct > 100"))
            self.check("SENSOR:mass_null_iff_fault_or_absent", "mass_kg NULL iff quality_flag in (SENSOR_FAULT, NO_WEIGHT_SENSOR)", "blocking",
                       self.q(f"SELECT count(*) FROM {te} WHERE (mass_kg IS NULL) <> (quality_flag IN ('SENSOR_FAULT','NO_WEIGHT_SENSOR'))"))
            self.check("SENSOR:uncertainty_null_iff_mass_null", "mass_uncertainty_kg NULL iff mass_kg NULL", "blocking",
                       self.q(f"SELECT count(*) FROM {te} WHERE (mass_uncertainty_kg IS NULL) <> (mass_kg IS NULL)"))
            self.check("SENSOR:not_installed_consistent", "NOT_INSTALLED status only (and always) on devices without weight measurement", "blocking",
                       self.q(f"SELECT count(*) FROM {te} t JOIN {dv} d USING (device_id) WHERE (t.sensor_status='NOT_INSTALLED') <> (NOT d.has_weight_measurement)"))
            self.check("SENSOR:duplicates_identical_payload", "duplicate deliveries carry identical measurement payload", "blocking",
                       self.q(f"SELECT count(*) FROM (SELECT message_id FROM {te} GROUP BY message_id HAVING count(DISTINCT (fill_pct, coalesce(mass_kg,-1e9), measured_at)) > 1)"))
        if ce:
            self.check("TIME:collection_actual_after_order", "actual_at > order_placed_at", "blocking",
                       self.q(f"SELECT count(*) FROM {ce} WHERE actual_at IS NOT NULL AND order_placed_at IS NOT NULL AND actual_at < order_placed_at"))
            self.check("TIME:order_before_schedule", "order_placed_at <= scheduled_at", "blocking",
                       self.q(f"SELECT count(*) FROM {ce} WHERE order_placed_at IS NOT NULL AND order_placed_at > scheduled_at"))
            self.check("SEM:actual_iff_executed", "actual_at present iff COMPLETED/PARTIAL/WASTED_TRIP", "blocking",
                       self.q(f"SELECT count(*) FROM {ce} WHERE (actual_at IS NOT NULL) <> (status IN ('COMPLETED','PARTIAL','WASTED_TRIP'))"))
            self.check("SEM:device_estimate_consistent", "device_estimated_collected_kg = before - after when both present, NULL otherwise", "blocking",
                       self.q(f"""SELECT count(*) FROM {ce} WHERE (device_estimated_collected_kg IS NULL) <> (device_mass_kg_before IS NULL OR device_mass_kg_after IS NULL)
                              OR abs(device_estimated_collected_kg - (device_mass_kg_before - device_mass_kg_after)) > 0.11"""))
            # contract validity: exactly one version per service date
            self.check("CONTRACT:one_version_per_event", "each executed event matches exactly one contract version by local date", "blocking",
                       self.q(f"""SELECT count(*) FROM (SELECT c.collection_id, count(v.contract_version_id) k FROM {ce} c
                              LEFT JOIN {cv} v ON v.contract_id = c.contract_id
                              AND CAST(timezone('Europe/Helsinki', coalesce(c.actual_at, c.scheduled_at)) AS DATE) >= v.effective_from
                              AND (v.effective_to IS NULL OR CAST(timezone('Europe/Helsinki', coalesce(c.actual_at, c.scheduled_at)) AS DATE) < v.effective_to)
                              GROUP BY 1 HAVING k <> 1)"""))
        if cv:
            self.check("CONTRACT:versions_contiguous", "versions contiguous (effective_to = next effective_from) and only last open", "blocking",
                       self.q(f"""SELECT count(*) FROM (SELECT effective_to, lead(effective_from) OVER (PARTITION BY contract_id ORDER BY version_no) nx FROM {cv})
                              WHERE (nx IS NULL AND effective_to IS NOT NULL) OR (nx IS NOT NULL AND effective_to IS DISTINCT FROM nx)"""))
        ct, wb = self.v("reference/contracts"), self.v("operations/weighbridge_tickets")
        if dv and ct:
            self.check("MAT:contract_material_matches_device", "contract material = device material", "blocking",
                       self.q(f"SELECT count(*) FROM {ct} c JOIN {dv} d USING (device_id) WHERE c.material_stream <> d.material_stream"))
            self.check("MAT:equipment_compatible", "biowaste only in COMBI units; mixed_plastic only in DUO units; classes are COMBI/DUO", "blocking",
                       self.q(f"""SELECT count(*) FROM {dv} WHERE (material_stream='biowaste' AND equipment_class<>'COMBI')
                              OR (material_stream='mixed_plastic' AND equipment_class<>'DUO') OR equipment_class NOT IN ('COMBI','DUO')"""))
            self.check("MAT:equipment_volume_limit", "container size within the Europress class limit: COMBI <= 22 m3, DUO <= 30 m3", "blocking",
                       self.q(f"""SELECT count(*) FROM {dv} WHERE (equipment_class='COMBI' AND container_volume_m3 > 22)
                              OR (equipment_class='DUO' AND container_volume_m3 > 30)"""))
            mc = self.v("reference/material_classes")
            if mc:
                self.check("MAT:credit_only_cardboard_plastics", "only cardboard and plastics are credit-eligible (Europress review)", "blocking",
                           self.q(f"""SELECT count(*) FROM {mc} WHERE credit_eligible <> (material_stream IN ('cardboard','plastic_film','mixed_plastic'))"""))
                il_ = self.v("finance/invoice_lines")
                if il_:
                    self.check("MAT:no_credit_on_chargeable", "no MATERIAL_CREDIT line on a chargeable stream", "blocking",
                               self.q(f"""SELECT count(*) FROM {il_} l JOIN {self.v('finance/invoices')} i USING (invoice_id)
                                      JOIN {ct} c USING (contract_id) JOIN {mc} m USING (material_stream)
                                      WHERE l.line_type='MATERIAL_CREDIT' AND NOT m.credit_eligible"""))
            self.check("DEV:on_call_majority", "most devices are emptied on call (Europress review)", "blocking",
                       0 if self.q(f"SELECT avg(CASE WHEN collection_policy='ON_CALL' THEN 1.0 ELSE 0 END) FROM {dv}") >= 0.5 else 1)
        if wb and ce:
            self.check("WB:material_matches", "ticket material_declared = device material", "blocking",
                       self.q(f"SELECT count(*) FROM {wb} w JOIN {ce} c USING (operator_job_ref) JOIN {dv} d ON d.device_id=c.device_id WHERE w.material_declared <> d.material_stream"))
            self.check("WB:arrival_after_collection", "ticket arrival after the lift", "blocking",
                       self.q(f"SELECT count(*) FROM {wb} w JOIN {ce} c USING (operator_job_ref) WHERE w.arrival_at < c.actual_at"))
            self.check("WB:published_after_arrival", "published_at >= arrival_at", "blocking", self.q(f"SELECT count(*) FROM {wb} WHERE published_at < arrival_at"))
            self.check("WB:net_is_gross_minus_tare", "net_kg = gross_kg - tare_kg", "blocking", self.q(f"SELECT count(*) FROM {wb} WHERE net_kg <> gross_kg - tare_kg"))
            self.check("WB:allocation_sums", "allocated nets of a weighing event sum to its net", "blocking",
                       self.q(f"SELECT count(*) FROM (SELECT weighing_event_id, any_value(net_kg) n, sum(allocated_net_kg) s, count(*) k, any_value(loads_on_vehicle) l FROM {wb} GROUP BY 1) WHERE k = l AND n <> s"))
            self.check("WB:only_completed_lifts", "tickets only for COMPLETED/PARTIAL events", "blocking",
                       self.q(f"SELECT count(*) FROM {wb} w JOIN {ce} c USING (operator_job_ref) WHERE c.status NOT IN ('COMPLETED','PARTIAL')"))
        wo = self.v("operations/maintenance_work_orders")
        if wo:
            self.check("TIME:workorder_order", "started_at <= completed_at", "blocking", self.q(f"SELECT count(*) FROM {wo} WHERE completed_at < started_at"))

    # ------------------------------------------------------------------ physics (private truth)
    def physics(self):
        td, tc, th = self.v("truth/truth_device", "priv"), self.v("truth/truth_collections", "priv"), self.v("truth/truth_hourly_state", "priv")
        if td and tc:
            n = self.q(f"""SELECT count(*) FROM {td} d LEFT JOIN (SELECT device_id, sum(true_collected_kg + true_side_waste_collected_kg) c FROM {tc} GROUP BY 1) x USING (device_id)
                       WHERE abs(d.true_total_inflow_kg - coalesce(x.c,0) - d.true_end_container_kg - d.true_end_side_stock_kg) > 0.01 + 1e-6 * d.true_total_inflow_kg""")
            self.check("PHYS:mass_balance", "inflow = collected + side collected + end container + end side stock (per device)", "blocking", n)
        if tc:
            self.check("PHYS:non_negative", "no negative true masses", "blocking",
                       self.q(f"SELECT count(*) FROM {tc} WHERE true_mass_before_kg < -1e-6 OR true_collected_kg < -1e-6 OR true_residual_kg < -1e-6 OR true_side_waste_collected_kg < -1e-6"))
            self.check("PHYS:collected_plus_residual", "mass_before = collected + residual", "blocking",
                       self.q(f"SELECT count(*) FROM {tc} WHERE abs(true_mass_before_kg - true_collected_kg - true_residual_kg) > 1e-3"))
        if th:
            self.check("PHYS:hourly_bounds", "true fill in [0,100], masses >= 0", "blocking",
                       self.q(f"SELECT count(*) FROM {th} WHERE true_fill_pct < -1e-3 OR true_fill_pct > 100.001 OR true_container_mass_kg < -1e-3 OR true_side_stock_kg < -1e-3"))
            self.check("PHYS:no_mass_increase_without_inflow", "container mass never increases in an hour without inflow", "blocking",
                       self.q(f"""SELECT count(*) FROM (SELECT true_container_mass_kg m, true_inflow_kg i,
                              lag(true_container_mass_kg) OVER (PARTITION BY device_id ORDER BY hour_start_at) p FROM {th}) WHERE p IS NOT NULL AND m > p + 0.01 AND i < 1e-6"""))
        ce, wa = self.v("operations/collection_events"), self.v("truth/weighbridge_all", "priv")
        if tc and ce:
            self.check("PHYS:truth_only_for_lifts", "truth_collections only for COMPLETED/PARTIAL events", "blocking",
                       self.q(f"SELECT count(*) FROM {tc} t LEFT JOIN (SELECT collection_id, status FROM {ce} UNION ALL SELECT collection_id, status FROM {self.v('operations/collection_events','hold') or ce}) c USING (collection_id) WHERE c.status IS NULL OR c.status NOT IN ('COMPLETED','PARTIAL')"))
        if wa and tc:
            self.check("PHYS:weighbridge_close_to_truth", "single-load WEIGHED tickets within 100 kg of true net (>5 sigma)", "blocking",
                       self.q(f"SELECT count(*) FROM {wa} WHERE loads_on_vehicle=1 AND tare_method='WEIGHED' AND abs(net_kg - true_net_kg) > 100"))

    # ------------------------------------------------------------------ finance
    def finance(self):
        inv, il = self.v("finance/invoices"), self.v("finance/invoice_lines")
        if inv and il:
            self.check("FIN:invoice_total_equals_lines", "invoice total = sum of line amounts (to the cent)", "blocking",
                       self.q(f"SELECT count(*) FROM {inv} i JOIN (SELECT invoice_id, round(sum(amount_eur),2) s, count(*) n FROM {il} GROUP BY 1) l USING (invoice_id) WHERE abs(i.total_eur - l.s) > 0.004 OR i.n_lines <> l.n"))
            self.check("FIN:line_amount_sign", "credits negative, charges positive", "blocking",
                       self.q(f"SELECT count(*) FROM {il} WHERE (line_type='MATERIAL_CREDIT' AND amount_eur > 0) OR (line_type<>'MATERIAL_CREDIT' AND amount_eur < 0)"))
            self.check("TIME:invoice_after_period", "invoice issued after its billing period", "blocking",
                       self.q(f"SELECT count(*) FROM {inv} WHERE CAST(issued_at AS DATE) < CAST(billing_period || '-01' AS DATE) + INTERVAL 1 MONTH - INTERVAL 1 DAY"))
        for pkg, key in (("pub", "labels_dev/reference_economics"), ("priv", "labels_test/reference_economics")):
            re_ = self.v(key, pkg)
            if not re_:
                continue
            self.check(f"FIN:{pkg}:net_identity", "net = credit - collection - processing - penalties; total = -net", "blocking",
                       self.q(f"""SELECT count(*) FROM {re_} WHERE abs(net_material_contribution_eur - (material_credit_eur - collection_cost_eur - processing_cost_eur - penalties_eur)) > 0.004
                              OR abs(total_customer_cost_eur + net_material_contribution_eur) > 0.004 OR abs(expected_invoice_amount_eur - total_customer_cost_eur) > 0.004"""))
            self.check(f"FIN:{pkg}:per_tonne_null_iff_no_mass", "EUR/t NULL iff billing mass NULL or 0; otherwise = cost / t", "blocking",
                       self.q(f"""SELECT count(*) FROM {re_} WHERE (collection_cost_eur_per_t IS NULL) <> (billing_mass_kg IS NULL OR billing_mass_kg = 0)
                              OR abs(collection_cost_eur_per_t - collection_cost_eur / (billing_mass_kg/1000)) > 0.006"""))
            rl = self.v(key.replace("reference_economics", "reference_charge_lines"), pkg)
            if rl:
                self.check(f"FIN:{pkg}:reference_lines_sum", "sum of reference lines = expected invoice amount", "blocking",
                           self.q(f"SELECT count(*) FROM {re_} e LEFT JOIN (SELECT collection_id, sum(amount_eur) s FROM {rl} GROUP BY 1) l USING (collection_id) WHERE abs(coalesce(l.s,0) - e.expected_invoice_amount_eur) > 0.004"))
        lab = self.v("truth/invoice_line_labels", "priv")
        r1, r2 = self.v("labels_dev/reference_economics"), self.v("labels_test/reference_economics", "priv")
        if inv and lab and r1 and r2:
            # every euro of difference between billed and expected is explained by a labelled discrepancy
            n = self.q(f"""WITH exp AS (SELECT contract_id, strftime(service_date, '%Y-%m') m, sum(expected_invoice_amount_eur) e FROM (SELECT * FROM {r1} UNION ALL SELECT * FROM {r2}) GROUP BY 1,2),
                    rent AS (SELECT i.invoice_id, coalesce(sum(l.amount_eur),0) r FROM {inv} i LEFT JOIN {il} l ON l.invoice_id=i.invoice_id AND l.line_type='RENTAL' GROUP BY 1),
                    d AS (SELECT invoice_id, sum(delta_cents)/100.0 dl FROM {lab} WHERE discrepancy_type NOT LIKE 'RENTAL%' GROUP BY 1)
                    SELECT count(*) FROM {inv} i JOIN rent USING (invoice_id) LEFT JOIN exp ON exp.contract_id=i.contract_id AND exp.m=i.billing_period
                    LEFT JOIN d USING (invoice_id) WHERE abs(i.total_eur - rent.r - coalesce(exp.e,0) - coalesce(d.dl,0)) > 0.011""")
            self.check("FIN:invoice_reconciles_to_labels", "billed - expected per invoice equals the sum of labelled discrepancies", "blocking", n)

    # ------------------------------------------------------------------ splits / leakage / privacy
    def leakage(self):
        dv_pub = self.v("reference/devices")
        dv_hold = self.v("reference/devices", "hold")
        if dv_pub and dv_hold:
            self.check("SPLIT:no_holdout_devices_public", "holdout devices absent from all public tables", "blocking",
                       self.q(f"SELECT count(*) FROM {dv_pub} WHERE device_id IN (SELECT device_id FROM {dv_hold})"))
            for key in ("telemetry/telemetry_hourly", "operations/collection_events", "telemetry/telemetry_daily_summary", "benchmark/decision_cases", "labels_dev/anomaly_labels"):
                t = self.v(key)
                if t:
                    self.check(f"SPLIT:holdout_absent:{key}", "no holdout device rows", "blocking",
                               self.q(f"SELECT count(*) FROM {t} WHERE device_id IN (SELECT device_id FROM {dv_hold})"))
            inv = self.v("finance/invoices")
            self.check("SPLIT:holdout_absent:invoices", "no holdout customer invoices", "blocking",
                       self.q(f"SELECT count(*) FROM {inv} WHERE customer_id IN (SELECT customer_id FROM {dv_hold})"))
        lab = self.v("labels_dev/anomaly_labels")
        if lab:
            meta = json.load(open(self.pub / "metadata" / "dataset_manifest.json"))
            a, b = meta["label_periods"]["validation"][1], meta["label_periods"]["test"][1]
            self.check("SPLIT:dev_labels_before_test", "public labels only from train/validation periods", "blocking",
                       self.q(f"SELECT count(*) FROM {lab} WHERE timezone('Europe/Helsinki', eval_at) >= TIMESTAMP '{a}'"))
            self.check("SPLIT:dev_period_labels_ended_before_test", "public device-period labels end before the test period", "blocking",
                       self.q(f"SELECT count(*) FROM {lab} WHERE entity_type IN ('device_period','device') AND (end_at IS NULL OR timezone('Europe/Helsinki', end_at) >= TIMESTAMP '{a}')"))
            ce_, inv_ = self.v("operations/collection_events"), self.v("finance/invoices")
            if ce_ and inv_:
                self.check("SPLIT:dev_economics_not_billed_in_test", "no public reference economics for events billed on test-period invoices", "blocking",
                           self.q(f"""SELECT count(*) FROM {self.v('labels_dev/reference_economics')} e JOIN {inv_} i ON i.contract_id = e.contract_id
                                  AND i.billing_period = strftime(e.service_date, '%Y-%m') WHERE e.expected_invoice_amount_eur <> 0 AND timezone('Europe/Helsinki', i.issued_at) >= TIMESTAMP '{a}'"""))
            re_ = self.v("labels_dev/reference_economics")
            self.check("SPLIT:dev_economics_before_test", "public reference economics only train/validation", "blocking",
                       self.q(f"SELECT count(*) FROM {re_} WHERE timezone('Europe/Helsinki', eval_at) >= TIMESTAMP '{a}'"))
        dc = self.v("benchmark/decision_cases")
        if dc:
            self.check("SPLIT:no_private_cases_public", "no test_private decision cases in public", "blocking",
                       self.q(f"SELECT count(*) FROM {dc} WHERE split = 'test_private'"))
            dt = self.v("labels_dev/decision_truth")
            self.check("SPLIT:no_test_decision_truth_public", "no test decision truth in public", "blocking",
                       self.q(f"SELECT count(*) FROM {dt} WHERE split NOT IN ('train','validation')"))
        # private-only columns must not appear in public non-label tables
        bad = []
        for (pkg, key), name in self.views.items():
            if pkg != "pub" or key.startswith("labels_dev"):
                continue
            for c in TABLES[key]["cols"]:
                if c["name"].startswith("true_") or "scenario" in c["name"] or c["name"] in ("collection_id",) and key == "operations/weighbridge_tickets":
                    bad.append(f"{key}.{c['name']}")
        self.check("LEAK:no_truth_columns_in_public_features", "no true_*/scenario columns in public feature tables", "blocking", len(bad), bad or None)
        priv_files = [p for p in self.pub.rglob("*") if "private" in p.name.lower()
                      or any(part in ("truth", "labels_test", "holdout_full") for part in p.relative_to(self.pub).parts)]
        self.check("LEAK:no_private_files_in_public", "no private/truth files inside public package", "blocking", len(priv_files),
                   [str(p) for p in priv_files] or None)
        # PII scan over all string columns of public tables
        hits = {}
        for (pkg, key), name in self.views.items():
            if pkg != "pub":
                continue
            for c in TABLES[key]["cols"]:
                if c["type"] != "str":
                    continue
                for pn, rx in PII_PATTERNS.items():
                    n = self.q(f"SELECT count(*) FROM (SELECT DISTINCT {c['name']} v FROM {name}) WHERE regexp_matches(v, '{rx}')")
                    if n:
                        hits[f"{key}.{c['name']}:{pn}"] = n
        self.check("PRIV:no_personal_data_patterns", "no emails, phone numbers, personal ids, IBANs in public strings", "blocking", sum(hits.values()), hits or None)
        cu = self.v("reference/customers")
        if cu:
            self.check("PRIV:fictional_customer_names", "all customer names are marked fictional", "blocking",
                       self.q(f"SELECT count(*) FROM {cu} WHERE customer_name NOT LIKE 'Fictional %'"))

    def snapshot(self):
        for snap in sorted(self.priv.glob("holdout_asof_*")) if self.priv.exists() else []:
            cut = snap.name.split("_")[-1]
            c = f"TIMESTAMPTZ '{cut} 00:00:00 Europe/Helsinki'"
            rules = {"telemetry/telemetry_hourly.parquet": "received_at", "operations/weighbridge_tickets.parquet": "published_at",
                     "operations/quality_assessments.parquet": "published_at", "finance/invoices.parquet": "issued_at",
                     "operations/collection_events.parquet": "coalesce(actual_at, scheduled_at)", "operations/maintenance_work_orders.parquet": "reported_at"}
            n = 0
            for rel, col in rules.items():
                f = snap / rel
                if f.exists():
                    n += self.q(f"SELECT count(*) FROM '{f}' WHERE {col} >= {c}")
            f = snap / "telemetry" / "telemetry_daily_summary.parquet"
            if f.exists():
                n += self.q(f"SELECT count(*) FROM '{f}' WHERE date >= DATE '{cut}'")
            f = snap / "operations" / "collection_events.parquet"
            if f.exists():
                n += self.q(f"SELECT count(*) FROM '{f}' WHERE weight_reconciliation_status <> 'UNKNOWN_AS_OF' OR invoice_match_status <> 'UNKNOWN_AS_OF'")
            self.check(f"SPLIT:asof_snapshot_no_future:{snap.name}", "as-of snapshot contains nothing knowable only after the cutoff", "blocking", n)

    def metadata(self):
        for root in (self.pub, self.priv):
            mf = root / "metadata" / "dataset_manifest.json"
            if not root.exists():
                continue
            if not mf.exists():
                self.check(f"META:{root.name}:manifest", "manifest present", "blocking", 1)
                continue
            m = json.load(open(mf))
            bad = [f["path"] for f in m["files"] if not (root / f["path"]).exists() or sha256_file(root / f["path"]) != f["sha256"]]
            self.check(f"META:{root.name}:checksums", "manifest checksums match files", "blocking", len(bad), bad[:10] or None)
            for k in ("synthetic", "generator_version", "seed", "config_hash", "dataset_status"):
                self.check(f"META:{root.name}:{k}", f"manifest has {k}", "blocking", 0 if k in m else 1)
            self.check(f"META:{root.name}:synthetic_flag", "manifest declares synthetic and no real customer data", "blocking",
                       0 if (m.get("synthetic") is True and m.get("contains_real_customer_data") is False) else 1)

    # ------------------------------------------------------------------ plausibility (warnings)
    def plausibility(self):
        ce, te = self.v("operations/collection_events"), self.v("telemetry/telemetry_hourly")
        tc = self.v("truth/truth_collections", "priv")
        stats = {}
        if tc:
            med = self.q(f"SELECT median(true_fill_before_pct) FROM {tc}")
            stats["median_true_fill_at_lift_pct"] = round(med, 1)
            self.check("PLAUS:median_fill", "median true fill at lift in [40, 90] %", "warning", 0 if 40 <= med <= 90 else 1, round(med, 1))
            ov = self.q(f"SELECT avg(CASE WHEN cycle_full_hours > 0 THEN 1 ELSE 0 END) FROM {tc}")
            stats["share_cycles_with_overflow"] = round(ov, 3)
            self.check("PLAUS:overflow_share", "share of cycles reaching 100 % in [2, 25] %", "warning", 0 if 0.02 <= ov <= 0.25 else 1, round(ov, 3))
        if te:
            n, u = self.con.execute(f"SELECT count(*), count(DISTINCT message_id) FROM {te}").fetchone()
            dup = (n - u) / n
            stats["telemetry_rows"], stats["duplicate_rate"] = n, round(dup, 4)
            self.check("PLAUS:duplicate_rate", "duplicate delivery rate in (0, 2] %", "warning", 0 if 0 < dup <= 0.02 else 1, round(dup, 4))
            expected = self.q(f"SELECT sum(datediff('hour', a, b) + 1) FROM (SELECT device_id, min(measured_at) a, max(measured_at) b FROM {te} GROUP BY 1)")
            miss = 1 - u / expected
            stats["missing_message_rate"] = round(miss, 4)
            self.check("PLAUS:missing_rate", "missing measurement rate in [0.5, 10] %", "warning", 0 if 0.005 <= miss <= 0.10 else 1, round(miss, 4))
        re_ = self.v("labels_dev/reference_economics")
        dv = self.v("reference/devices")
        if re_:
            rows = self.con.execute(f"SELECT d.material_stream, median(collection_cost_eur_per_t) FROM {re_} e JOIN {dv} d USING (device_id) WHERE collection_cost_eur_per_t IS NOT NULL GROUP BY 1").fetchall()
            stats["median_collection_cost_eur_per_t"] = {k: round(v, 1) for k, v in rows}
            self.check("PLAUS:cost_per_t_range", "median collection EUR/t per material in [20, 400]", "warning",
                       sum(1 for k, v in rows if not 20 <= v <= 400), stats["median_collection_cost_eur_per_t"])
        lab = [self.v("labels_dev/anomaly_labels"), self.v("labels_test/anomaly_labels", "priv")]
        lab = [x for x in lab if x]
        if lab:
            u = " UNION ALL ".join(f"SELECT label_family, scenario_id, severity, is_actionable FROM {x}" for x in lab)
            fams = self.con.execute(f"SELECT label_family, count(*) FROM ({u}) GROUP BY 1 ORDER BY 2 DESC").fetchall()
            stats["label_counts"] = dict(fams)
        self.stats = stats

    def coverage(self):
        """Evidence counts per scenario family (normal / borderline / clear where labels exist)."""
        cov = {}
        labs = [x for x in (self.v("labels_dev/anomaly_labels"), self.v("labels_test/anomaly_labels", "priv")) if x]
        if labs:
            u = " UNION ALL ".join(f"SELECT scenario_id, label_family, severity, is_actionable FROM {x}" for x in labs)
            for sid, sev, n in self.con.execute(f"SELECT scenario_id, severity, count(*) FROM ({u}) WHERE scenario_id IS NOT NULL GROUP BY 1,2").fetchall():
                cov.setdefault(sid, {})[sev] = n
            for fam, sev, n in self.con.execute(f"SELECT label_family, severity, count(*) FROM ({u}) WHERE scenario_id IS NULL GROUP BY 1,2").fetchall():
                sid = {"OUTDATED_TARIFF": "S23", "DUPLICATE_LINE": "S25", "WRONG_SURCHARGE": "S24", "MISSING_LINE": "S26",
                       "UNMATCHED_LINE": "S26", "UNINVOICED_COLLECTION": "S26", "WEIGHT_BASIS_MISMATCH": "S26"}.get(fam)
                if sid:
                    cov.setdefault(sid, {})[sev] = cov.get(sid, {}).get(sev, 0) + n
        ce, te, wb = self.v("operations/collection_events"), self.v("telemetry/telemetry_hourly"), self.v("operations/weighbridge_tickets")
        st, pi, cv = self.v("reference/sites"), self.v("reference/price_index_monthly"), self.v("reference/contract_versions")

        def ev(sid, n):
            cov.setdefault(sid, {})["evidence"] = int(n or 0)
        if st:
            ev("S04", self.q(f"SELECT count(*) FROM {st} WHERE region_code IN ('FI-19','FI-17')"))
            ev("S30", self.q(f"SELECT count(*) FROM (SELECT site_id FROM {self.v('reference/devices')} GROUP BY 1 HAVING count(*) >= 2)"))
        if pi:
            ev("S05", self.q(f"SELECT count(*) FROM {pi} p WHERE material='cardboard' AND price_eur_per_t < 0.7 * (SELECT median(price_eur_per_t) FROM {pi} WHERE material='cardboard')"))
            ev("S06", self.q(f"SELECT count(*) FROM {pi} p WHERE material='plastic_film' AND price_eur_per_t > 1.3 * (SELECT median(price_eur_per_t) FROM {pi} WHERE material='plastic_film')"))
        if ce:
            ev("S21", self.q(f"SELECT count(*) FROM {ce} WHERE status IN ('CANCELLED_BY_CUSTOMER','SKIPPED_LOW_FILL')"))
            ev("S22", self.q(f"SELECT count(*) FROM {ce} WHERE status='PARTIAL'"))
            ev("S37", self.q(f"SELECT count(*) FROM {ce} WHERE status='WASTED_TRIP'"))
            ev("S11", self.q(f"SELECT count(DISTINCT site_id) FROM {self.v('reference/site_calendar')} WHERE closure_reason='PLANNED_CLOSURE'"))
            ev("S09", self.q(f"SELECT count(DISTINCT site_id) FROM {self.v('reference/site_calendar')} WHERE closure_reason='SUMMER_SHUTDOWN'"))
            ev("S10", self.q(f"SELECT count(*) FROM {self.v('reference/site_calendar')} WHERE public_holiday_name IS NOT NULL"))
            ev("S33", self.q(f"SELECT count(*) FROM {ce} c JOIN {self.v('reference/devices')} d USING (device_id) WHERE NOT d.has_weight_measurement AND c.weight_reconciliation_status='WEIGHBRIDGE_NOT_AVAILABLE'"))
        if te:
            ev("S17", self.q(f"SELECT count(*) - count(DISTINCT message_id) FROM {te}"))
            ev("S16", self.q(f"SELECT count(*) FROM {te} WHERE received_at > measured_at + INTERVAL 1 HOUR"))
            ev("S18", self.q(f"SELECT count(*) FROM (SELECT measured_at, lag(measured_at) OVER (PARTITION BY device_id ORDER BY ingest_seq) p FROM {te}) WHERE measured_at < p"))
            ev("S12", self.q(f"SELECT count(*) FROM {te} WHERE mass_kg IS NULL"))
        if wb:
            ev("S19", self.q(f"SELECT count(*) FROM {wb} WHERE published_at > arrival_at + INTERVAL 7 DAY"))
        if cv:
            ev("S23", self.q(f"SELECT count(*) FROM {cv} WHERE version_no > 1"))
        dts = [x for x in (self.v("labels_dev/decision_truth"), self.v("labels_test/decision_truth", "priv")) if x]
        if dts:
            u = " UNION ALL ".join(f"SELECT * FROM {x}" for x in dts)
            ev("S31", self.q(f"SELECT count(*) FROM ({u}) WHERE near_threshold"))
            ev("S34", self.q(f"SELECT count(*) FROM ({u}) WHERE constraint_conflict"))
            ev("S35", self.q(f"SELECT count(*) FROM ({u}) WHERE hidden_cost_trap_present"))
            ev("S36", self.q(f"SELECT count(*) FROM ({u}) WHERE best_action='NO_ACTION'"))
        self.coverage_map = cov
        present = sum(1 for k, v in cov.items() if sum(v.values()) > 0)
        self.check("COV:scenario_families_present", "at least 30 scenario families with evidence", "warning" if present >= 30 else "blocking",
                   0 if present >= 30 else 30 - present, present)

    def run(self):
        for f in (self.structural, self.semantic, self.physics, self.finance, self.leakage, self.snapshot, self.metadata, self.plausibility, self.coverage):
            f()
        blocking = [r for r in self.results if r["level"] == "blocking" and not r["passed"]]
        warn = [r for r in self.results if r["level"] == "warning" and not r["passed"]]
        return {"data_dir": str(self.d), "n_checks": len(self.results), "blocking_failures": len(blocking),
                "warnings": len(warn), "release_ok": len(blocking) == 0, "stats": getattr(self, "stats", {}),
                "scenario_coverage": getattr(self, "coverage_map", {}), "checks": self.results}


def write_report(rep: dict, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "validation_report.json", "w") as fh:
        json.dump(rep, fh, indent=2, default=str)
    lines = [f"# Validation summary — {Path(rep['data_dir']).name}", "",
             f"* Checks run: **{rep['n_checks']}**", f"* Release-blocking failures: **{rep['blocking_failures']}**",
             f"* Plausibility warnings: **{rep['warnings']}**", f"* Release OK: **{rep['release_ok']}**", "", "## Failed checks", ""]
    failed = [r for r in rep["checks"] if not r["passed"]]
    lines += [f"* `{r['check_id']}` ({r['level']}): {r['description']} — {r['violations']} ({r['detail']})" for r in failed] or ["None."]
    lines += ["", "## Key statistics", "", "```json", json.dumps(rep["stats"], indent=1, default=str), "```", "",
              "## All checks", "", "| check | level | violations |", "|---|---|---|"]
    lines += [f"| {r['check_id']} | {r['level']} | {r['violations']} |" for r in rep["checks"]]
    (out_dir / "validation_summary.md").write_text("\n".join(lines))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="quickstart")
    ap.add_argument("--data", default=None)
    a = ap.parse_args(argv)
    d = Path(a.data) if a.data else ROOT / "data" / a.profile
    rep = V(d).run()
    write_report(rep, ROOT / "reports" / (a.profile if not a.data else Path(a.data).name))
    print(f"checks={rep['n_checks']} blocking_failures={rep['blocking_failures']} warnings={rep['warnings']}")
    for r in rep["checks"]:
        if not r["passed"]:
            print(f"  FAIL [{r['level']}] {r['check_id']}: {r['violations']} {str(r['detail'])[:200]}")
    return 0 if rep["release_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
