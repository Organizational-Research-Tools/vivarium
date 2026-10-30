
import pandas as pd

df = pd.read_csv('records.csv')
modules = ['base_sheet', 'secondary_sheet', 'binder_system', 'additive_package_1', 
           'additive_package_2', 'additive_package_3', 'process_profile_1', 
           'process_profile_2', 'process_profile_3', 'surface_treatment', 
           'joint_system', 'conditioning_step']

recipes = df[['prototype_id', 'project'] + modules].drop_duplicates('prototype_id')

# Panel means per prototype/test - only full 6-specimen panels
panel_df = df[df['kind'] == 'qualification'].groupby(['project', 'prototype_id', 'test']).agg(
    mean=('value', 'mean'),
    cnt=('value', 'count')
).reset_index()

# Pivot to wide
wide = panel_df.pivot_table(index=['project','prototype_id'], columns='test', values='mean').reset_index()
wide.columns.name = None
# Rename columns
col_map = {'seal hold temperature': 'heat', 'edge crush resistance': 'strength', 'wet strength retained': 'water'}
wide = wide.rename(columns=col_map)

# Merge recipes
summary = wide.merge(recipes, on='prototype_id', how='left')

# Compute margins
heat_thresh, heat_step = 77.5, 0.25
str_thresh, str_step = 7.1, 0.03
water_thresh, water_step = 78.0, 0.4

if 'heat' in summary.columns:
    summary['h_mrg'] = (summary['heat'] - heat_thresh) / heat_step
if 'strength' in summary.columns:
    summary['s_mrg'] = (summary['strength'] - str_thresh) / str_step
if 'water' in summary.columns:
    summary['w_mrg'] = (summary['water'] - water_thresh) / water_step

summary['weakest'] = summary[['h_mrg','s_mrg','w_mrg']].min(axis=1)

print("=== COMPLETE PANEL RESULTS (sorted by weakest margin) ===")
cols = ['project_x','prototype_id','secondary_sheet','heat','strength','water','h_mrg','s_mrg','w_mrg','weakest']
# find which project col
proj_col = [c for c in summary.columns if 'project' in c.lower()][0]
print(summary.rename(columns={proj_col:'project'}).sort_values('weakest', ascending=False)[
    ['project','prototype_id','secondary_sheet','heat','strength','water','h_mrg','s_mrg','w_mrg','weakest']
].to_string(index=False, float_format='%.2f'))
