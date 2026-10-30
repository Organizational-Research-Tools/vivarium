import pandas as pd
x=pd.read_csv('records.csv'); cols=['prototype_id','instrument','value','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
for p in ['QP-9259','QP-5174','QP-9273']:
 z=x[x.project==p].drop_duplicates('prototype_id')[cols]
 print('\n'+p); print(z.to_string(index=False))