import pandas as pd
r=pd.read_csv('records.csv')
pr='QP-6879'
q=r[r.project==pr].groupby(['prototype_id','test']).agg(n=('value','count'),m=('value','mean')).reset_index().pivot(index='prototype_id',columns='test',values='m')
recipe_cols=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
rec=r[r.project==pr].groupby('prototype_id')[recipe_cols].first()
print(q.sort_values('seal hold temperature',ascending=False).join(rec).to_string())