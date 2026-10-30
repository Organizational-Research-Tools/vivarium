import pandas as pd
x=pd.read_csv('records.csv')
for p in ['p_K6ZM59ZMJM','p_K6ZM59ZMJT','p_K6ZM59ZMJP','p_K6ZM59ZMJR']:
 d=x[x.prototype_id==p]
 print('\n',p, len(d))
 if len(d):
  print(d[['kind','instrument','test','value','measured_by']].to_string(index=False))
  print(d[['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].drop_duplicates().to_string(index=False))