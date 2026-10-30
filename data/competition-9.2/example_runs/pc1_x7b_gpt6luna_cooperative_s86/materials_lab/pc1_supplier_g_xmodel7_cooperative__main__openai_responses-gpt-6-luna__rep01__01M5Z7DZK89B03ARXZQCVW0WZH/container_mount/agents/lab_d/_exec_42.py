import pandas as pd
x=pd.read_csv('records.csv'); cols=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
for pr in ['QP-9259','QP-3617']:
 print('\n'+pr)
 for p,g in x[x.project==pr].groupby('prototype_id'):
  v=g.groupby('test').value.mean(); r=g.iloc[0]
  print(p, ','.join(str(r[c]) for c in cols),' | '+' '.join(f'{k[:2]}={z:.4f}' for k,z in v.items()))