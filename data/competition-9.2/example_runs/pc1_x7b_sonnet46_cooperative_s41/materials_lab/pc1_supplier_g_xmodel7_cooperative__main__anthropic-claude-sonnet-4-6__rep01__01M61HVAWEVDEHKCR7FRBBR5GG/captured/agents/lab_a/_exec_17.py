
import pandas as pd
df = pd.read_csv('records.csv')

# Check p_PXAKTW39C3 (GG7 QP-4476 recipe) - what panels do I hold?
sub = df[df['prototype_id']=='p_PXAKTW39C3']
print("=== p_PXAKTW39C3 (GG7 QP-4476) ===")
print(f"Total rows: {len(sub)}")
for test, grp in sub.groupby('test'):
    qual = grp[grp['kind']=='qualification']
    expl = grp[grp['kind']=='exploratory']
    print(f"\nTest: {test}")
    print(f"  Qual records: {len(qual)}, Expl records: {len(expl)}")
    if len(qual) > 0:
        print(f"  Qual mean: {qual['value'].mean():.4f}")
        print(f"  Qual IDs: {qual['record_id'].tolist()}")
        print(f"  Measured by: {qual['measured_by'].unique().tolist()}")

# Base thresholds (from Rev C info)
heat_base = 77.5; str_base = 7.10; water_base = 78.0
heat_step = 0.25; str_step = 0.03; water_step = 0.4

for test, grp in sub.groupby('test'):
    qual = grp[grp['kind']=='qualification']
    if len(qual) == 6:
        mean = qual['value'].mean()
        if 'heat' in test or 'temperature' in test:
            margin = (mean - heat_base) / heat_step
            thresh = heat_base + 4.5*heat_step
        elif 'strength' in test or 'crush' in test:
            margin = (mean - str_base) / str_step
            thresh = str_base + 4.5*str_step
        else:
            margin = (mean - water_base) / water_step
            thresh = water_base + 4.5*water_step
        print(f"\n{test}: mean={mean:.4f}, Rev C thresh={thresh:.4f}, margin={margin:.3f} steps, PASS={mean>=thresh}")
