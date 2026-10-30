import pandas as pd
x=pd.read_csv('records.csv')
# unique prototypes known with project and recipe; candidates other than QP9219
cols=['project','prototype_id','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
u=x.dropna(subset=['base_sheet']).drop_duplicates('prototype_id')[cols]
print(u[u.project!='QP-9219'].to_string(index=False))
print('\nreadings non9219:')
print(x[x.project!='QP-9219'][['project','prototype_id','kind','instrument','value','measured_by']].to_string(index=False))