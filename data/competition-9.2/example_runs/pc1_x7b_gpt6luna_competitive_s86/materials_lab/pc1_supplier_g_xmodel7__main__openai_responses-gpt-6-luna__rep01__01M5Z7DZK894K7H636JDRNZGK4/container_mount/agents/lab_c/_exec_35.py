import pandas as pd
r=pd.read_csv('records.csv')
x=r[r.project.eq('QP-6879')]
for p,g in x.groupby('prototype_id'):
  print(p, g[['base_sheet','secondary_sheet','binder_system','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].drop_duplicates().head(1).to_dict('records')[0], ' heat',g[g.test.eq('seal hold temperature')].value.mean(), 'strength',g[g.test.eq('edge crush resistance')].value.mean(), 'water',g[g.test.eq('wet strength retained')].value.mean(), 'n',g.groupby('test').size().to_dict())