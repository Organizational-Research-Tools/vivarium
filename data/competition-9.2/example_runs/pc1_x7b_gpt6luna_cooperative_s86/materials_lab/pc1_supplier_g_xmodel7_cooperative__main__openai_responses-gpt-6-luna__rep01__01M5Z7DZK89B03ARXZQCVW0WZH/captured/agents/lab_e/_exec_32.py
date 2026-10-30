import pandas as pd
x=pd.read_csv('records.csv'); mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
for proj in ['QP-6879','QP-9980']:
 q=x[x.project==proj].drop_duplicates('prototype_id')
 print('\n',proj)
 print(q[['prototype_id']+mods].to_string(index=False))