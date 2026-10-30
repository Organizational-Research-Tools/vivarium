import pandas as pd
x=pd.read_csv('records.csv')
y=x[x.project.eq('QP-7092')]
print(y.groupby(['prototype_id','instrument','test','kind']).agg(n=('value','size'),mean=('value','mean')).to_string())
print('\nrecipes:')
print(y.drop_duplicates('prototype_id')[['prototype_id','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].to_string(index=False))