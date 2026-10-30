import pandas as pd
x=pd.read_csv('records.csv')
for p in ['p_EGTGJGD3PY','p_K6ZM59ZMJT','p_K6ZM59ZMJM','p_K6ZM59ZMJP','p_K6ZM59ZMJR']:
 y=x[x.prototype_id==p]
 print('\n',p, 'rows',len(y))
 if not y.empty:
  print(y[['record_id','project','kind','instrument','value','measured_by']].to_string(index=False))
  print(y.iloc[0][['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].to_dict())