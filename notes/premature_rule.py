"""C05 · Idea for a better PREMATURE_UNJUSTIFIED rule, scored against the baseline.

Run from repo root after the Task B baseline has written its predictions:
  python baselines/b2_rules_anomaly.py data/quickstart/public my_task_b.csv
  python notes/premature_rule.py data/quickstart/public my_task_b.csv
  (competition: write the baseline to e.g. /tmp/comp_b.csv first and pass data/competition/public)

The baseline only flags SCHEDULED lifts below 40 % fill. On on-call devices it misses two mechanisms:
  * S39 precautionary orders: CUSTOMER_REQUEST at low fill just before a weekend or a closed day.
  * S40 fill sensor reads falsely high: an ON_CALL_ORDER fires on a high fill reading, but the weight
    shows the container was far from full.
The extra rule adds both. It only ADDS predictions; it does not change the baseline file.
"""
import sys; sys.path.insert(0, 'src'); sys.path.insert(0, 'baselines')
import warnings; warnings.filterwarnings('ignore')
from pathlib import Path
import pandas as pd
from b2_rules_anomaly import collection_features
from europress_data.sdk import open_dataset
from europress_data.evaluate import score_b

root, base_csv = Path(sys.argv[1]), sys.argv[2]
f = collection_features(root)
con = open_dataset(root)
cal = con.sql("SELECT site_id, date, is_open FROM site_calendar").df()
con.close()

f['local_date'] = f.actual_at.dt.tz_convert('Europe/Helsinki').dt.date
nxt = cal.assign(local_date=(pd.to_datetime(cal.date) - pd.Timedelta(days=1)).dt.date)  # row = the NEXT day's calendar
f = f.merge(nxt[['site_id', 'local_date', 'is_open']].rename(columns={'is_open': 'next_day_open'}), on=['site_id', 'local_date'], how='left')
dow = pd.to_datetime(f.local_date).dt.dayofweek

# the device's own typical full load: median device-estimated kg on lifts that started >= 70 % full
typical = (f[(f.status == 'COMPLETED') & (f.device_fill_pct_before >= 70)]
           .groupby('device_id').device_estimated_collected_kg.median().rename('typical_full_kg'))
f = f.merge(typical, on='device_id', how='left')
share_of_full = f.device_estimated_collected_kg.fillna(f.mass_kg) / f.typical_full_kg
done = f.status.isin(['COMPLETED', 'PARTIAL'])

before_closed_day = (dow >= 4) | (f.next_day_open == False)  # Fri/Sat/Sun lift, or the site is closed tomorrow
precautionary = done & (f.collection_policy == 'ON_CALL') & (f.trigger_type == 'CUSTOMER_REQUEST') \
    & (f.device_fill_pct_before < 45) & before_closed_day
false_high = done & (f.trigger_type == 'ON_CALL_ORDER') & (share_of_full < 0.4)

base = pd.read_csv(base_csv)
extra = pd.DataFrame({'entity_type': 'collection', 'entity_id': f.loc[precautionary | false_high, 'collection_id'],
                      'label_family': 'PREMATURE_UNJUSTIFIED'})
new = pd.concat([base, extra]).drop_duplicates()
keys = ['positives', 'predicted', 'tp', 'precision', 'recall', 'f1', 'explained_flagged_as_anomaly']
for split in ['validation', 'all']:
    a, b = score_b(base, root / 'labels_dev', split), score_b(new, root / 'labels_dev', split)
    print(f"{split:10s} baseline {[a['PREMATURE_UNJUSTIFIED'][k] for k in keys]}  macro_f1 {a['macro_f1']}")
    print(f"{'':10s} new      {[b['PREMATURE_UNJUSTIFIED'][k] for k in keys]}  macro_f1 {b['macro_f1']}")
print('columns:', keys)
print(f'extra flags: precautionary {int(precautionary.sum())}, false-high fill {int(false_high.sum())}')
