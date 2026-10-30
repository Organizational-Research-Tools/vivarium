
import pandas as pd
df = pd.read_csv('records.csv')

# Check all strength qualification panels
print("=== Strength qualification panels (Rev C threshold: 7.235 kN/m) ===")
str_thresh = 7.235
for pid, grp in df.groupby('prototype_id'):
    str_grp = grp[(grp['test'].str.contains('crush|strength', case=False)) & (grp['kind']=='qualification')]
    if len(str_grp) >= 6:
        mean = str_grp['value'].mean()
        proj = grp['project'].iloc[0]
        recipe_cols = ['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2',
                       'additive_package_3','process_profile_1','process_profile_2','process_profile_3',
                       'surface_profile','surface_treatment','joint_system','conditioning_step']
        recipe_cols_actual = [c for c in recipe_cols if c in grp.columns]
        recipe = {c: grp.iloc[0].get(c,'?') for c in recipe_cols_actual}
        status = '✅' if mean >= str_thresh else f'❌ (gap {str_thresh-mean:.4f})'
        print(f"  {pid} ({proj}): mean={mean:.4f} {status}")
        print(f"    recipe: {recipe}")
        print(f"    IDs: {str_grp['record_id'].tolist()}")

# Also check all heat panels for Rev C
print("\n=== Heat qualification panels (Rev C threshold: 78.625°C) ===")
heat_thresh = 78.625
for pid, grp in df.groupby('prototype_id'):
    h_grp = grp[(grp['test'].str.contains('heat|temperature', case=False)) & (grp['kind']=='qualification')]
    if len(h_grp) >= 6:
        mean = h_grp['value'].mean()
        proj = grp['project'].iloc[0]
        status = '✅' if mean >= heat_thresh else f'❌ (gap {heat_thresh-mean:.4f})'
        print(f"  {pid} ({proj}): mean={mean:.4f} {status}")

# Check water panels for Rev C
print("\n=== Water qualification panels (Rev C threshold: 79.8%) ===")
water_thresh = 79.8
for pid, grp in df.groupby('prototype_id'):
    w_grp = grp[(grp['test'].str.contains('wet|water', case=False)) & (grp['kind']=='qualification')]
    if len(w_grp) >= 6:
        mean = w_grp['value'].mean()
        proj = grp['project'].iloc[0]
        status = '✅' if mean >= water_thresh else f'❌ (gap {water_thresh-mean:.4f})'
        print(f"  {pid} ({proj}): mean={mean:.4f} {status}")
