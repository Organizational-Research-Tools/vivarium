import pandas as pd
x=pd.read_csv('records.csv');print(x.shape);print(x.groupby(['project','test']).size().unstack(fill_value=0).to_string())
print('\nStrength recipes & means')
s=x[x.test.eq('edge crush resistance')].groupby(['project','prototype_id']).agg(mean=('value','mean'),n=('value','size')).reset_index();
cols=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
r=x.drop_duplicates(['project','prototype_id'])[['project','prototype_id']+cols];print(s.merge(r,on=['project','prototype_id']).to_string(index=False))