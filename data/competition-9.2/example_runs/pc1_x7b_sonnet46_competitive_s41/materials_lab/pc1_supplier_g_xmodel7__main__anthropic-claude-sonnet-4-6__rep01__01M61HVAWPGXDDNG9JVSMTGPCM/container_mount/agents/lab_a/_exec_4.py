
import pandas as pd
import numpy as np

df = pd.read_csv('records.csv')

recipe_cols = ['base_sheet', 'secondary_sheet', 'binder_system', 'additive_package_1',
               'additive_package_2', 'additive_package_3', 'process_profile_1', 'process_profile_2',
               'process_profile_3', 'surface_treatment', 'joint_system', 'conditioning_step']

# Get panel means per prototype per test
panels = df[df['kind'] == 'qualification'].groupby(['project', 'prototype_id', 'test'])['value'].mean().reset_index()
panels.columns = ['project', 'prototype_id', 'test', 'mean']
panels_wide = panels.pivot_table(index=['project', 'prototype_id'], columns='test', values='mean').reset_index()
panels_wide.columns.name = None
panels_wide.rename(columns={
    'edge crush resistance': 'strength',
    'seal hold temperature': 'heat',
    'wet strength retained': 'water'
}, inplace=True)

# Add recipe info
recipes = df.dropna(subset=recipe_cols).groupby(['project', 'prototype_id'])[recipe_cols].first().reset_index()
summary = panels_wide.merge(recipes, on=['project', 'prototype_id'], how='left')

# Define thresholds
heat_thresh = 77.5
str_thresh = 7.1
water_thresh = 78.0

summary['heat_ok'] = summary['heat'] >= heat_thresh
summary['str_ok'] = summary['strength'] >= str_thresh
summary['water_ok'] = summary['water'] >= water_thresh
summary['all_ok'] = summary['heat_ok'] & summary['str_ok'] & summary['water_ok']
summary['has_GG7'] = summary['secondary_sheet'] == 'GG7'

# Show summary grouped by prototype (one row per prototype with all 3 tests where available)
# First let's group by prototype to see full-panel results
proto_summary = df.dropna(subset=recipe_cols).groupby(['project', 'prototype_id'])[recipe_cols].first().reset_index()
merged = proto_summary.merge(panels_wide, on=['project', 'prototype_id'], how='left')
merged['heat_ok'] = merged['heat'] >= heat_thresh
merged['str_ok'] = merged['strength'] >= str_thresh
merged['water_ok'] = merged['water'] >= water_thresh
merged['all_ok'] = merged['heat_ok'] & merged['str_ok'] & merged['water_ok']
merged['has_GG7'] = merged['secondary_sheet'] == 'GG7'

print("=== PROTOTYPE SUMMARY ===")
cols_show = ['project', 'prototype_id', 'has_GG7', 'heat', 'strength', 'water', 'heat_ok', 'str_ok', 'water_ok', 'all_ok']
print(merged[cols_show].to_string())
