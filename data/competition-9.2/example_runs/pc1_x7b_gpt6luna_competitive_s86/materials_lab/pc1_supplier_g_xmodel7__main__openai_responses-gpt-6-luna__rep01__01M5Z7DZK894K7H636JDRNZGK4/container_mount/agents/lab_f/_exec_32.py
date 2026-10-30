import pandas as pd
x=pd.read_csv('records.csv')
for p in ['p_T2SEB0BAET','p_K6ZM59ZMJM','p_K6ZM59ZMJT']:
 d=x[x.prototype_id==p]
 print('\n',p, len(d))
 if len(d):
  print(d[['kind','project','instrument','measured_by','requester','specimen','value','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].to_string(index=False))
