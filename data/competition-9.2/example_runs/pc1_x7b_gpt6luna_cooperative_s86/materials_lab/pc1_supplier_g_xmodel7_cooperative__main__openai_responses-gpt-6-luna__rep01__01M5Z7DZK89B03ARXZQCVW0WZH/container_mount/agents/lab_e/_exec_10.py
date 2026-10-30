import pandas as pd
x=pd.read_csv('records.csv')
for p in ['p_NQYNDKZ3CG','p_NQYNDKZ3CJ']:
 y=x[(x.prototype_id==p)&(x.kind=='qualification')]
 print('\n',p)
 print(y.groupby(['test','measured_by']).value.agg(['mean','min','max']).to_string())
 print(y[['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].drop_duplicates().to_string(index=False))