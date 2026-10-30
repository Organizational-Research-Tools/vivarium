
import pandas as pd
df = pd.read_csv('records.csv')

# Check QP-4476 prototypes with recipes we know
module_cols = ['base_sheet','secondary_sheet','binder_system','additive_package_1',
               'additive_package_2','additive_package_3','process_profile_1',
               'process_profile_2','process_profile_3','surface_treatment',
               'joint_system','conditioning_step']

pl57 = df[df['project'] == 'QP-4476'].copy()
# Per prototype, per test means
summary = pl57.groupby(['prototype_id','test'])['value'].mean().unstack('test')
summary.columns = [c.replace(' ','_').replace('(','').replace(')','') for c in summary.columns]
print("QP-4476 prototype means (new Rev B thresholds: heat≥78.25, str≥7.19, water≥79.20):")
print(summary)

# Check recipes we know
recipes = pl57.drop_duplicates('prototype_id')[['prototype_id'] + module_cols]
print("\nKnown QP-4476 recipes:")
print(recipes.to_string())

# Key: p_WEMQRN3Q9M (my heat prototype) recipe
wem = recipes[recipes['prototype_id']=='p_WEMQRN3Q9M']
print("\np_WEMQRN3Q9M recipe:", wem[module_cols].values.tolist())

# Check what rev B impacts: which candidates we have that might still work
print("\n--- REV B ANALYSIS ---")
print("p_WEMQRN3Q9M heat mean:", pl57[pl57['prototype_id']=='p_WEMQRN3Q9M']['value'].mean())
# Q15KX5S0ZB strength
print("p_Q15KX5S0ZB strength mean:", pl57[pl57['prototype_id']=='p_Q15KX5S0ZB']['value'].mean())
# Q15KX5S0ZP water
print("p_Q15KX5S0ZP water mean:", pl57[pl57['prototype_id']=='p_Q15KX5S0ZP']['value'].mean())

# All three of the above use GG7 - need to assess non-GG7 options
# p_XV6JQRAVAV heat
xvav = pl57[pl57['prototype_id']=='p_XV6JQRAVAV']
if len(xvav) > 0:
    print("p_XV6JQRAVAV heat mean:", xvav['value'].mean())
