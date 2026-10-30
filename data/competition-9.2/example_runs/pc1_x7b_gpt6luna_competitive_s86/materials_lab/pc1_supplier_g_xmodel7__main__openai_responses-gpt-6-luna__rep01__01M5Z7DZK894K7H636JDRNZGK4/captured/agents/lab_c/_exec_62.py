import pandas as pd
r=pd.read_csv('records.csv')
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
x=r[r.project.isin(['QP-3617','QP-6879','QP-9273'])]
print(x.groupby(['project','prototype_id','kind','test','measured_by']).agg(n=('value','size'),mean=('value','mean')).to_string())