
import pandas as pd
import numpy as np

df = pd.read_csv('records.csv')

modules = ['base_sheet', 'secondary_sheet', 'binder_system', 'additive_package_1',
           'additive_package_2', 'additive_package_3', 'process_profile_1',
           'process_profile_2', 'process_profile_3', 'surface_treatment',
           'joint_system', 'conditioning_step']

# Get panel means by prototype and test
panel_means = df[df['kind'] == 'qualification'].groupby(
    ['project', 'prototype_id', 'test']
)['value'].mean().unstack('test')

# Also get recipe info
recipe_info = df[df['kind'] == 'qualification'].groupby('prototype_id')[modules].first()

# Merge
panel_means = panel_means.reset_index()
panel_means = panel_means.merge(recipe_info, on='prototype_id', how='left')

# Thresholds
heat_thresh = 77.5
strength_thresh = 7.1
water_thresh = 78.0

if 'seal hold temperature' in panel_means.columns:
    panel_means.rename(columns={'seal hold temperature': 'heat', 
                                 'edge crush resistance': 'strength',
                                 'wet strength retained': 'water'}, inplace=True)

print("Columns:", panel_means.columns.tolist())
print()

# Check which recipes have all 3 tests
complete = panel_means.dropna(subset=['heat', 'strength', 'water'])
complete = complete.copy()
complete['pass_heat'] = complete['heat'] >= heat_thresh
complete['pass_strength'] = complete['strength'] >= strength_thresh
complete['pass_water'] = complete['water'] >= water_thresh
complete['all_pass'] = complete['pass_heat'] & complete['pass_strength'] & complete['pass_water']
complete['has_GG7'] = complete['secondary_sheet'] == 'GG7'

print("=== Complete recipes (all 3 tests) ===")
for _, row in complete.iterrows():
    status = "PASS" if row['all_pass'] else "FAIL"
    gg7 = " [GG7]" if row['has_GG7'] else ""
    print(f"{row['project']} | {row['prototype_id'][:12]}{gg7} | "
          f"heat={row['heat']:.2f}({'✓' if row['pass_heat'] else '✗'}) "
          f"str={row['strength']:.3f}({'✓' if row['pass_strength'] else '✗'}) "
          f"water={row['water']:.2f}({'✓' if row['pass_water'] else '✗'}) | {status}")
