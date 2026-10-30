
import pandas as pd
import numpy as np

df = pd.read_csv("records.csv")

# Aggregate to prototype level
modules = ['base_sheet','secondary_sheet','binder_system','additive_package_1',
           'additive_package_2','additive_package_3','process_profile_1','process_profile_2',
           'process_profile_3','surface_treatment','joint_system','conditioning_step']

# Get mean per prototype per test (qualification panels only)
quals = df[df['kind']=='qualification'].copy()
grp = quals.groupby(['project','prototype_id','test','measured_by'])['value'].mean().reset_index()
pivot = grp.pivot_table(index=['project','prototype_id'], columns='test', values='value').reset_index()
pivot.columns.name = None

# Rename columns
col_map = {'edge crush resistance':'strength_kNm',
           'seal hold temperature':'heat_C',
           'wet strength retained':'water_pct'}
pivot = pivot.rename(columns=col_map)

# Merge recipe info
recipe_info = df[modules + ['prototype_id']].drop_duplicates('prototype_id')
pivot = pivot.merge(recipe_info, on='prototype_id', how='left')

# Evaluate pass/fail
pivot['pass_heat'] = pivot.get('heat_C', np.nan) >= 77.5
pivot['pass_str']  = pivot.get('strength_kNm', np.nan) >= 7.10
pivot['pass_water']= pivot.get('water_pct', np.nan) >= 78.0
pivot['has_GG7'] = pivot['secondary_sheet'] == 'GG7'

# Compute margin in steps (step sizes: heat=0.25, strength=0.03, water=0.4)
pivot['margin_heat']  = (pivot.get('heat_C',     np.nan) - 77.5) / 0.25
pivot['margin_str']   = (pivot.get('strength_kNm', np.nan) - 7.10) / 0.03
pivot['margin_water'] = (pivot.get('water_pct',   np.nan) - 78.0) / 0.4

pivot['weakest_margin'] = pivot[['margin_heat','margin_str','margin_water']].min(axis=1)
pivot['all_pass'] = pivot['pass_heat'] & pivot['pass_str'] & pivot['pass_water']

print("=== QUALIFICATION PANEL RESULTS FROM PRIOR SESSION ===")
print(f"Total prototypes with data: {len(pivot)}")
print()

# Sort by project and all_pass
for proj in sorted(pivot['project'].unique()):
    sub = pivot[pivot['project']==proj].sort_values('weakest_margin', ascending=False)
    print(f"--- {proj} ---")
    for _, row in sub.iterrows():
        gg7 = " [GG7!]" if row['has_GG7'] else ""
        h = f"{row.get('heat_C',float('nan')):.2f}°C" if 'heat_C' in row and not pd.isna(row['heat_C']) else "heat:?"
        s = f"{row.get('strength_kNm',float('nan')):.3f}kN" if 'strength_kNm' in row and not pd.isna(row['strength_kNm']) else "str:?"
        w = f"{row.get('water_pct',float('nan')):.2f}%" if 'water_pct' in row and not pd.isna(row['water_pct']) else "water:?"
        wm = f"weakest={row['weakest_margin']:.2f}steps" if not pd.isna(row['weakest_margin']) else "incomplete"
        ok = "✓ALL PASS" if row['all_pass'] else "✗"
        print(f"  {row['prototype_id']}{gg7}: {h} {s} {w} → {wm} {ok}")
    print()
