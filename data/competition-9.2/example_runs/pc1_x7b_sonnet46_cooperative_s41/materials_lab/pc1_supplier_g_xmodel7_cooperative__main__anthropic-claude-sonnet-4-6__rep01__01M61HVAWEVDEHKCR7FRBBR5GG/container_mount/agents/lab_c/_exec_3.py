
import pandas as pd
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 300)

df = pd.read_csv('records.csv')

# Get unique recipes per project (by prototype groups - same recipe appears under main prototype)
# The my_records output tells us which prototype IDs belong together
# Let's get composition for each prototype
comp_cols = ['base_sheet','secondary_sheet','binder_system','additive_package_1',
             'additive_package_2','additive_package_3','process_profile_1',
             'process_profile_2','process_profile_3','surface_treatment',
             'joint_system','conditioning_step']

# Get panel means per prototype per test
panels = df[df['kind']=='qualification'].groupby(
    ['project','prototype_id','test']
)['value'].mean().reset_index()
panels.columns = ['project','prototype_id','test','mean']

# Pivot
pivot = panels.pivot_table(index=['project','prototype_id'], columns='test', values='mean')
pivot.columns = ['strength','heat','water']
pivot = pivot.reset_index()

# Get composition for each prototype (first row suffices since it's the same for all specimens)
comp = df[comp_cols + ['prototype_id']].drop_duplicates('prototype_id')

# Merge
full = pivot.merge(comp, on='prototype_id', how='left')

# Thresholds
H, S, W = 77.5, 7.1, 78.0

full['h_pass'] = full['heat'] >= H
full['s_pass'] = full['strength'] >= S
full['w_pass'] = full['water'] >= W

print("Complete recipe analysis:")
print(full[['project','prototype_id','heat','strength','water','h_pass','s_pass','w_pass','secondary_sheet'] + comp_cols].to_string())
