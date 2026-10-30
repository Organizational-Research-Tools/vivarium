
import pandas as pd

df = pd.read_csv('records.csv')

recipe_cols = ['base_sheet', 'secondary_sheet', 'binder_system', 'additive_package_1',
               'additive_package_2', 'additive_package_3', 'process_profile_1', 'process_profile_2',
               'process_profile_3', 'surface_treatment', 'joint_system', 'conditioning_step']

recipes = df.dropna(subset=['base_sheet']).drop_duplicates('prototype_id')[['prototype_id', 'project'] + recipe_cols]

# Key insight analysis: what distinguishes strength-passing vs failing?
# strength panels available:
strength_panels = df[df['test']=='edge crush resistance'].groupby('prototype_id')['value'].mean()

# merge with recipe
recipe_strength = recipes.merge(strength_panels.rename('strength'), on='prototype_id')
recipe_strength['pass_strength'] = recipe_strength['strength'] >= 7.10
print("Strength analysis:")
print(recipe_strength[['prototype_id', 'strength', 'pass_strength', 'secondary_sheet', 'binder_system', 
                        'process_profile_2', 'surface_treatment', 'base_sheet', 'process_profile_3']].to_string())

print("\n--- Water analysis ---")
water_panels = df[df['test']=='wet strength retained'].groupby('prototype_id')['value'].mean()
recipe_water = recipes.merge(water_panels.rename('water'), on='prototype_id')
recipe_water['pass_water'] = recipe_water['water'] >= 78.0
print(recipe_water[['prototype_id', 'water', 'pass_water', 'base_sheet', 'secondary_sheet', 'binder_system',
                     'process_profile_3', 'surface_treatment', 'process_profile_2']].to_string())
