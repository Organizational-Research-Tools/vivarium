
import pandas as pd
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 200)

df = pd.read_csv('records.csv')

# Get panel results per prototype per project per test
panels = df[df['kind'] == 'qualification'].groupby(
    ['project', 'prototype_id', 'test']
)['value'].agg(['mean', 'count']).reset_index()
panels.columns = ['project', 'prototype_id', 'test', 'mean', 'count']

# Pivot to get one row per prototype
pivot = panels.pivot_table(index=['project','prototype_id'], columns='test', values='mean').reset_index()
pivot.columns.name = None
print("Panel means by prototype:")
print(pivot.to_string())

# Thresholds
heat_thresh = 77.5
strength_thresh = 7.1
water_thresh = 78.0

print("\n--- PASS/FAIL ASSESSMENT ---")
for _, row in pivot.iterrows():
    h = row.get('seal hold temperature', None)
    s = row.get('edge crush resistance', None)
    w = row.get('wet strength retained', None)
    
    h_pass = h >= heat_thresh if pd.notna(h) else '?'
    s_pass = s >= strength_thresh if pd.notna(s) else '?'
    w_pass = w >= water_thresh if pd.notna(w) else '?'
    
    status = "ALL PASS" if (h_pass is True and s_pass is True and w_pass is True) else "FAIL"
    
    print(f"{row['project']} | {row['prototype_id']} | H:{h:.3f if pd.notna(h) else 'N/A':>7} {'✓' if h_pass is True else ('?' if h_pass=='?' else '✗')} | "
          f"S:{s:.4f if pd.notna(s) else 'N/A':>7} {'✓' if s_pass is True else ('?' if s_pass=='?' else '✗')} | "
          f"W:{w:.3f if pd.notna(w) else 'N/A':>7} {'✓' if w_pass is True else ('?' if w_pass=='?' else '✗')} | {status}")
