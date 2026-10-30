import pandas as pd
x=pd.read_csv('records.csv')
for p in ['p_HNZGFD3XEX','p_7S365TH6Y2']:
 y=x[x.prototype_id==p]
 print(p, len(y))
 print(y[['record_id','project','kind','instrument','value','measured_by','requester']].to_string(index=False))
 if len(y): print(y.iloc[0][['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].to_dict())