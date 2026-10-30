import pandas as pd
x=pd.read_csv('records.csv');
for p in ['QP-7092','QP-9980','QP-3617']:
 z=x[x.project==p]
 print('\n',p)
 for pid,g in z.groupby('prototype_id'):
  r=g.iloc[0]; comps=[r[c] for c in ['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']]
  print(pid, 'n',len(g),'tests',g.test.unique().tolist(),'mean',g.value.mean(),comps)
