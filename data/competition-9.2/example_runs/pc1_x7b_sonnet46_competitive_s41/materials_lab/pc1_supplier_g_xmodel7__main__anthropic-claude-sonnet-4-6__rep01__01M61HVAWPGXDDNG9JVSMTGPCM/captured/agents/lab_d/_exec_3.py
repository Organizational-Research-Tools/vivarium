
import pandas as pd

df = pd.read_csv('records.csv')

# Get unique recipe compositions per prototype
recipe_cols = ['base_sheet', 'secondary_sheet', 'binder_system', 'additive_package_1',
               'additive_package_2', 'additive_package_3', 'process_profile_1', 'process_profile_2',
               'process_profile_3', 'surface_treatment', 'joint_system', 'conditioning_step']

# Get one row per prototype (first row)
recipes = df.dropna(subset=['base_sheet']).drop_duplicates('prototype_id')[['prototype_id', 'project'] + recipe_cols]
print("Known recipe compositions:")
print(recipes.to_string())
print()

# Now look at strength values specifically
strength_df = df[df['test'] == 'edge crush resistance'][['prototype_id', 'project', 'kind', 'value', 'measured_by']]
strength_summary = strength_df.groupby(['project', 'prototype_id'])['value'].mean().reset_index()
strength_summary.columns = ['project', 'prototype_id', 'strength_mean']
print("Strength panel means:")
print(strength_summary.to_string())
