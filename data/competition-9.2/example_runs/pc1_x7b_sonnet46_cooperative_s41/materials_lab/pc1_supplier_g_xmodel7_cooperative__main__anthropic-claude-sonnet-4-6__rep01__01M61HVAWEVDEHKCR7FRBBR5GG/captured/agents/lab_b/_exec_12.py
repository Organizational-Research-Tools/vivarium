
import pandas as pd
df = pd.read_csv('records.csv')

# Rev C thresholds
T_heat = 78.625
T_str  = 7.235
T_wat  = 79.8
step_h, step_s, step_w = 0.25, 0.03, 0.4

print("=== ALL PANELS: REV C CHECK ===")
panels = df[df['kind']=='panel']
summary = panels.groupby(['project','prototype_id','test'])['value'].mean().reset_index()
summary.columns = ['project','prototype_id','test','mean']

# Pivot
piv = summary.pivot_table(index=['project','prototype_id'], columns='test', values='mean').reset_index()

recipe_cols = ['base_sheet','secondary_sheet','binder_system','additive_package_1',
               'additive_package_2','additive_package_3','process_profile_1',
               'process_profile_2','process_profile_3','surface_treatment',
               'joint_system','conditioning_step']

# Merge recipe info
recipe_df = df[['prototype_id'] + recipe_cols].dropna(subset=['base_sheet']).drop_duplicates('prototype_id')
piv = piv.merge(recipe_df, on='prototype_id', how='left')

for _, row in piv.iterrows():
    h = row.get('heat', None)
    s = row.get('strength', None)
    w = row.get('water', None)
    
    h_ok = h >= T_heat if pd.notna(h) else None
    s_ok = s >= T_str  if pd.notna(s) else None
    w_ok = w >= T_wat  if pd.notna(w) else None
    
    h_str = f"{h:.3f}{'✓' if h_ok else '✗'}" if pd.notna(h) else "---"
    s_str = f"{s:.4f}{'✓' if s_ok else '✗'}" if pd.notna(s) else "---"
    w_str = f"{w:.2f}{'✓' if w_ok else '✗'}" if pd.notna(w) else "---"
    
    # Compute weakest margin if all three present
    wm = ""
    if pd.notna(h) and pd.notna(s) and pd.notna(w):
        mh = (h - 77.5) / step_h
        ms = (s - 7.1)  / step_s
        mw = (w - 78.0) / step_w
        wm = f"  weakest={min(mh,ms,mw):.2f}steps"
    
    recipe = "/".join([str(row.get(c,'?')) for c in recipe_cols]) if pd.notna(row.get('base_sheet')) else ""
    print(f"{row['project']:8s} {row['prototype_id'][:14]} H={h_str} S={s_str} W={w_str}{wm}")
    if recipe:
        print(f"         recipe: {recipe}")
