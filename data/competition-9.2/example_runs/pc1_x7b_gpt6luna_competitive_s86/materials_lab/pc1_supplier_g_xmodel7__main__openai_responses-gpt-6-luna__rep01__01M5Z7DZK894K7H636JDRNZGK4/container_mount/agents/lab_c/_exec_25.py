import pandas as pd
x=pd.read_csv('records.csv')
cols=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
for proj,g in x.groupby('project'):
 print('\n',proj)
 print(g.groupby(['prototype_id','test','kind']).agg(n=('value','size'),mean=('value','mean')).reset_index().to_string(index=False))