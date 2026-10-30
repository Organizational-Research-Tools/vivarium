import pandas as pd
x=pd.read_csv('records.csv');
for p in ['QP-3617','QP-8807','QP-9980']:
 print('\n',p)
 z=x[x.project==p].groupby(['prototype_id','measured_by','test']).agg(n=('value','size'),mean=('value','mean'), recipe=('base_sheet', lambda s: '')).reset_index()
 comp_cols=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
 for pid,g in x[x.project==p].groupby('prototype_id'):
  r=g.iloc[0]; print(pid, r.measured_by, r.test, round(g.value.mean(),4), list(r[comp_cols]))