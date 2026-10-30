import pandas as pd
x=pd.read_csv('records.csv')
for t in ['seal hold temperature','edge crush resistance','wet strength retained']:
 g=x[x.test.eq(t)].groupby('prototype_id').agg(mean=('value','mean'), project=('project','first'))
 print('\n',t)
 for pid in g.sort_values('mean',ascending=False).head(15).index:
  r=x[x.prototype_id.eq(pid)].iloc[0]
  cols=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
  print(pid,g.loc[pid,'mean'],r['project'], [r[c] for c in cols])