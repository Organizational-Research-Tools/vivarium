
import pandas as pd
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 200)
pd.set_option('display.max_rows', 100)

df = pd.read_csv('records.csv')

# Get unique recipes per project with their compositions and panel means
modules = ['base_sheet','secondary_sheet','binder_system','additive_package_1',
           'additive_package_2','additive_package_3','process_profile_1',
           'process_profile_2','process_profile_3','surface_treatment',
           'joint_system','conditioning_step']

# Panel means by prototype and test
panels = df[df['kind']=='qualification'].groupby(['project','prototype_id','test'])['value'].mean().unstack('test')
panels.columns = [c.replace('seal hold temperature','heat').replace('edge crush resistance','strength').replace('wet strength retained','water') for c in panels.columns]
print("Panel means by prototype:")
print(panels.to_string())
print()

# Get compositions (first row per prototype)
comps = df.dropna(subset=['base_sheet']).drop_duplicates('prototype_id')[['prototype_id','project']+modules]
comps = comps.set_index('prototype_id')
print("Compositions:")
print(comps.to_string())
