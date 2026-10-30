
import pandas as pd
df = pd.read_csv('records.csv')

# Check p_WWXN5W4HZR (water panel for GG7 QP-4476)
print("=== p_WWXN5W4HZR water records ===")
sub = df[df['prototype_id']=='p_WWXN5W4HZR']
print(f"Total records: {len(sub)}")
for test, tg in sub.groupby('test'):
    qual = tg[tg['kind']=='qualification']
    print(f"  {test}: {len(qual)} qual, mean={qual['value'].mean():.4f}")
    print(f"  IDs: {qual['record_id'].tolist()}")

# Verify all three GG7 panels under Rev C
print("\n=== Rev C check for GG7 recipe (JA8, GG7, M2P, QJ2, 6FA, 44B, 62D, 2BR, N4L, 7KL, DL8, 3N8) ===")
heat_thresh, str_thresh, water_thresh = 78.625, 7.235, 79.8
heat_base, str_base, water_base = 77.5, 7.10, 78.0

# p_PXAKTW39C3 heat
h_data = df[(df['prototype_id']=='p_PXAKTW39C3') & (df['kind']=='qualification')]
h_mean = h_data['value'].mean()
h_margin = (h_mean - heat_base) / 0.25
print(f"Heat ({len(h_data)} records): mean={h_mean:.4f}°C {'✅' if h_mean>=heat_thresh else '❌'}, margin={h_margin:.3f} steps")
print(f"  IDs: {h_data['record_id'].tolist()}")

# p_6G7MJ89K4B strength
s_data = df[(df['prototype_id']=='p_6G7MJ89K4B') & (df['kind']=='qualification')]
s_mean = s_data['value'].mean()
s_margin = (s_mean - str_base) / 0.03
print(f"Strength ({len(s_data)} records): mean={s_mean:.4f} kN/m {'✅' if s_mean>=str_thresh else '❌'}, margin={s_margin:.3f} steps")
print(f"  IDs: {s_data['record_id'].tolist()}")

# p_WWXN5W4HZR water
w_data = df[(df['prototype_id']=='p_WWXN5W4HZR') & (df['kind']=='qualification')]
w_mean = w_data['value'].mean()
w_margin = (w_mean - water_base) / 0.4
print(f"Water ({len(w_data)} records): mean={w_mean:.4f}% {'✅' if w_mean>=water_thresh else '❌'}, margin={w_margin:.3f} steps")
print(f"  IDs: {w_data['record_id'].tolist()}")

weakest = min(h_margin, s_margin, w_margin)
print(f"\nWeakest margin: {weakest:.3f} steps (Rev C minimum: 4.5 steps)")
print(f"ALL PASS: {h_mean>=heat_thresh and s_mean>=str_thresh and w_mean>=water_thresh}")
