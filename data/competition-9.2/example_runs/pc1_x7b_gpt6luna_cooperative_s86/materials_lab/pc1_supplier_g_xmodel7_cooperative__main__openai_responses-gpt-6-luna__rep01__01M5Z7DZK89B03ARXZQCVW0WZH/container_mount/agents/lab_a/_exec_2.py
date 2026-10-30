import pandas as pd
D=pd.read_csv('records.csv')
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
print('rows',len(D),'protos',D.prototype_id.nunique(),'projects',D.project.unique())
wide=D.pivot_table(index=['project','prototype_id']+mods,columns='instrument',values='value',aggfunc='mean').reset_index()
print(wide.shape)
print(wide[['project','prototype_id','base_sheet','heat','strength','water']].to_string(index=False))
print('\nproto recipe count',D.groupby('prototype_id')[mods].first().drop_duplicates().shape)
print('\nmissing instruments',D.groupby('prototype_id').instrument.nunique().value_counts())