import pandas as pd
x=pd.read_csv('records.csv')
for p in ['p_Z398MDW5ST','p_5WCK5KFXM0','p_NPMVZ7VJMX','p_B7CX78CE96','p_B7CX78CE98','p_KBABVTJCX0']:
 d=x[x.prototype_id==p]
 if len(d):
  print('\n',p,d[['project','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].drop_duplicates().to_string(index=False))
  print(d.groupby(['test','measured_by']).value.mean())