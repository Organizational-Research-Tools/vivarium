
import pandas as pd
import numpy as np

df = pd.read_csv('records.csv')

# Get unique recipes per prototype
recipe_cols = ['base_sheet', 'secondary_sheet', 'binder_system', 'additive_package_1',
               'additive_package_2', 'additive_package_3', 'process_profile_1', 'process_profile_2',
               'process_profile_3', 'surface_treatment', 'joint_system', 'conditioning_step']

recipes = df.dropna(subset=recipe_cols).groupby(['project', 'prototype_id'])[recipe_cols].first().reset_index()
print("Recipes known:")
print(recipes.to_string())
