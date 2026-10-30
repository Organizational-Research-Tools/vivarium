
import pandas as pd
df = pd.read_csv('records.csv')

print("=== p_GR61XB2TYZ (QP-3089 GG7) — ALL RECORDS ===")
sub = df[df['prototype_id']=='p_GR61XB2TYZ']
print(f"Total records: {len(sub)}")
for test, tg in sub.groupby('test'):
    qual = tg[tg['kind']=='qualification']
    print(f"  {test}: {len(qual)}/6 qual specimens")
    if len(qual) > 0:
        print(f"    Mean: {qual['value'].mean():.4f}")
        print(f"    IDs: {qual['record_id'].tolist()}")

print("\n=== Rev C thresholds ===")
print("heat >= 78.625°C, strength >= 7.235 kN/m, water >= 79.8%")

# Check if strength records from lab_b are present
strength_ids = ['r_QYKNNDRFXJ','r_QYKNNDRFXK','r_QYKNNDRFXM','r_QYKNNDRFXN','r_QYKNNDRFXP','r_QYKNNDRFXQ']
heat_ids = ['r_GR61XB2TZ1','r_GR61XB2TZ2','r_GR61XB2TZ3','r_GR61XB2TZ4','r_GR61XB2TZ5','r_GR61XB2TZ6']
print(f"\nHeat records in my records: {sum(1 for r in heat_ids if r in df['record_id'].values)}/6")
print(f"Strength records in my records: {sum(1 for r in strength_ids if r in df['record_id'].values)}/6")
