
import pandas as pd
df = pd.read_csv('records.csv')

# My water receipts from the just-run panels
my_water = df[(df['measured_by'] == 'lab_f') & (df['instrument'] == 'water') & (df['kind'] == 'panel')]
print("My water panel receipts:")
for pid, grp in my_water.groupby('prototype_id'):
    recs = grp['record_id'].tolist()
    mean = grp['value'].mean()
    proj = grp['project'].iloc[0]
    margin = (mean - 79.2) / 0.4
    print(f"  {pid} ({proj}): mean={mean:.4f}% margin={margin:.2f} steps")
    print(f"    Receipts: {recs}")

print()
# Heat receipts I hold for key prototypes
heat = df[(df['instrument'] == 'heat') & (df['kind'] == 'panel')]
for pid in ['p_J6CX8AHRR3', 'p_S87ZV5EJH5', 'p_YD1Q0XW9SA']:
    sub = heat[heat['prototype_id'] == pid]
    if len(sub) > 0:
        recs = sub['record_id'].tolist()
        mean = sub['value'].mean()
        margin = (mean - 78.25) / 0.25
        print(f"  {pid} HEAT: mean={mean:.5f}°C margin={margin:.2f} steps receipts={recs}")

print()
# Strength receipts I hold
strength = df[(df['instrument'] == 'strength') & (df['kind'] == 'panel')]
for pid in ['p_J6CX8AHRR3', 'p_S87ZV5EJH5', 'p_YD1Q0XW9SA']:
    sub = strength[strength['prototype_id'] == pid]
    if len(sub) > 0:
        recs = sub['record_id'].tolist()
        mean = sub['value'].mean()
        margin = (mean - 7.19) / 0.03
        print(f"  {pid} STRENGTH: mean={mean:.5f} margin={margin:.2f} steps receipts={recs}")
    else:
        print(f"  {pid} STRENGTH: 0/6 in my records")

print()
# Check QP-6843 and QP-6572 granted prototypes
print("Projects with granted access (38 total):")
all_protos = df[['project','prototype_id']].drop_duplicates()
for proj in ['QP-6843','QP-6572','QP-4476']:
    sub = all_protos[all_protos['project'] == proj]
    print(f"  {proj}: {sub['prototype_id'].tolist()}")
