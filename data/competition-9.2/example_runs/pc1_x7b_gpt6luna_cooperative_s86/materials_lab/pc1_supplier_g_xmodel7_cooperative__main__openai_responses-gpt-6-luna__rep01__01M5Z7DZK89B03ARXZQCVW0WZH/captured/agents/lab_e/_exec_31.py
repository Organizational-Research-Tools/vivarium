import pandas as pd
x=pd.read_csv('records.csv')
q=x[x.project=='QP-9980']
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
# one row per proto test mean; list recipe + test mean
m=q.pivot_table(index=['prototype_id']+mods,columns='test',values='value',aggfunc='mean').reset_index()
print(m.to_string(index=False))