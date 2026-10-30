
import pandas as pd
import numpy as np

df = pd.read_csv('records.csv')

comp_cols = ['base_sheet', 'secondary_sheet', 'binder_system', 'additive_package_1',
             'additive_package_2', 'additive_package_3', 'process_profile_1', 'process_profile_2',
             'process_profile_3', 'surface_treatment', 'joint_system', 'conditioning_step']

# Get unique composition per prototype
comps = df.dropna(subset=['base_sheet']).drop_duplicates('prototype_id')[['prototype_id', 'project'] + comp_cols]

# Show all compositions
print(comps.to_string())
