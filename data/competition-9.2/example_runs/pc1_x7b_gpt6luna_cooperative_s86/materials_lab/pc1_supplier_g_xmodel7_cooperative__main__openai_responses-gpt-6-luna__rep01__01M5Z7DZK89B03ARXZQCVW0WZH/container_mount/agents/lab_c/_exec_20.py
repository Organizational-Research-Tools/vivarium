import pandas as pd
x=pd.read_csv('records.csv'); y=x[x.project.eq('QP-3617')]
cols=['prototype_id','test','value','measured_by']
for p,g in y.groupby('prototype_id'):
  m=g.groupby('test').value.mean().round(5).to_dict()
  row=g.iloc[0]
  r=[row[c] for c in ['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']]
  print(p,m,r)