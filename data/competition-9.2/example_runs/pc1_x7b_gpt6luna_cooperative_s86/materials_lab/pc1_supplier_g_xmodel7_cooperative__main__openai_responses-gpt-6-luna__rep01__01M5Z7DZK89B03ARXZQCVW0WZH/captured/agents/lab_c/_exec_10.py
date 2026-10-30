import pandas as pd
x=pd.read_csv('records.csv')
for proj in ['QP-5174','QP-9980','QP-8807','QP-7092','QP-3617','QP-9273']:
 d=x[x.project==proj]
 print('\n',proj)
 if d.empty: print('none');continue
 for pid,g in d.groupby('prototype_id'):
  means=g[g.kind=='qualification'].groupby('test').value.mean().round(4).to_dict()
  row=g.iloc[0]
  rec=[row[c] for c in ['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']]
  print(pid,means,rec)
