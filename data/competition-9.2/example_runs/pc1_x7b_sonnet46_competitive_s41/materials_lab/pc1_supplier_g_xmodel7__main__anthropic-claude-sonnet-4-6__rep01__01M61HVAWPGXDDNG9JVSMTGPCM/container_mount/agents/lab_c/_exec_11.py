
import pandas as pd
import numpy as np

df = pd.read_csv('records.csv')

# Show key PL-57 water results
pl57_projects = ['QP-4476', 'QP-6572', 'QP-6843']
water_records = df[df['test'] == 'water (wet strength retained, %)'].copy()

print("=== WATER RESULTS BY PROJECT ===")
for p in water_records['project'].unique():
    group = water_records[water_records['project'] == p]
    panels = group[group['kind'] == 'qualification']
    if not panels.empty:
        mean_val = panels['value'].mean()
        print(f"\n{p}: {len(panels)} panel readings, mean={mean_val:.4f}%")
        # Show recipe if available
        if 'base_sheet' in panels.columns and panels['base_sheet'].notna().any():
            row = panels.iloc[0]
            recipe = f"{row.get('base_sheet','?')}/{row.get('secondary_sheet','?')}/{row.get('binder_system','?')}/{row.get('additive_package_1','?')}/{row.get('additive_package_2','?')}/{row.get('additive_package_3','?')}/{row.get('process_profile_1','?')}/{row.get('process_profile_2','?')}/{row.get('process_profile_3','?')}/{row.get('surface_treatment','?')}/{row.get('joint_system','?')}/{row.get('conditioning_step','?')}"
            print(f"  Recipe: {recipe}")
        print(f"  Prototypes: {panels['prototype_id'].unique()}")

print("\n\n=== EXPLORATORY WATER READINGS ===")
exp = water_records[water_records['kind'] == 'exploratory']
for p in exp['project'].unique():
    g = exp[exp['project'] == p]
    print(f"\n{p}: {len(g)} exploratory readings, mean={g['value'].mean():.4f}%")
