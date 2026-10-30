
import pandas as pd

df = pd.read_csv('records.csv')
modules = ['base_sheet', 'secondary_sheet', 'binder_system', 'additive_package_1', 
           'additive_package_2', 'additive_package_3', 'process_profile_1', 
           'process_profile_2', 'process_profile_3', 'surface_treatment', 
           'joint_system', 'conditioning_step']

recipes = df[['prototype_id', 'project'] + modules].drop_duplicates('prototype_id')

# Panel summary: compute means per prototype/test
panels = df[df['kind'] == 'qualification'].groupby(['project', 'prototype_id', 'test']).agg(
    mean=('value', 'mean')
).unstack('test').reset_index()
panels.columns = ['project', 'prototype_id', 'heat', 'strength', 'water']

# Merge with recipes
summary = panels.merge(recipes, on='prototype_id', how='left')

# Compute margins
heat_thresh = 77.5; heat_step = 0.25
str_thresh = 7.1; str_step = 0.03
water_thresh = 78.0; water_step = 0.4

summary['heat_margin'] = (summary['heat'] - heat_thresh) / heat_step
summary['str_margin'] = (summary['strength'] - str_thresh) / str_step
summary['water_margin'] = (summary['water'] - water_thresh) / water_step
summary['weakest'] = summary[['heat_margin', 'str_margin', 'water_margin']].min(axis=1)

print("=== COMPLETE PANEL RESULTS ===")
print(summary[['project', 'prototype_id', 'secondary_sheet', 'heat', 'strength', 'water', 
               'heat_margin', 'str_margin', 'water_margin', 'weakest']].sort_values('weakest', ascending=False).to_string())
