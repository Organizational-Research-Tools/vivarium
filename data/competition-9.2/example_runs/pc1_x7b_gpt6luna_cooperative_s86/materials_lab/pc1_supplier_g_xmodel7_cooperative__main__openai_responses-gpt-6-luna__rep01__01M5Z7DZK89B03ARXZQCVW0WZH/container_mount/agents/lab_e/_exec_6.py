import pandas as pd
x=pd.read_csv('records.csv')
q=x[x.project.eq('QP-6879')]
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
for pid,g in q.groupby('prototype_id'):
  row=g.iloc[0]; d={m:row[m] for m in mods};
  means=g.groupby('test').value.mean().round(5).to_dict()
  print(pid,d,means)
