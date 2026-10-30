import pandas as pd
r=pd.read_csv('records.csv')
q=r[(r.project=='QP-6879') & (r.test=='seal hold temperature')]
cols=['prototype_id','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
print(q.groupby(cols).value.mean().sort_values(ascending=False).to_string())