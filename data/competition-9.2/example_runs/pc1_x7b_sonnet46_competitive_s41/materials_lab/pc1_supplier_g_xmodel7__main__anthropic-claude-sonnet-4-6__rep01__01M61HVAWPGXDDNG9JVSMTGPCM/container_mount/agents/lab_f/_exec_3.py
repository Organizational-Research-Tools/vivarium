
import pandas as pd

df = pd.read_csv('records.csv')

# Get unique recipes per prototype
modules = ['base_sheet', 'secondary_sheet', 'binder_system', 'additive_package_1', 
           'additive_package_2', 'additive_package_3', 'process_profile_1', 
           'process_profile_2', 'process_profile_3', 'surface_treatment', 
           'joint_system', 'conditioning_step']

recipes = df[['prototype_id', 'project'] + modules].drop_duplicates('prototype_id')
print(recipes[recipes['secondary_sheet'].notna()].to_string())
