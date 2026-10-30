import pandas as pd
x=pd.read_csv('records.csv')
for key in ['p_KCVBREJ1G9','G5','G9','p_SNNF91F2XB']:
 print('\n',key); z=x[x.prototype_id.astype(str).str.contains(key,case=False,na=False)]; print(z[['record_id','kind','project','prototype_id','test','value','measured_by']].to_string(index=False) if len(z) else 'none')
print('\nRecent rows:'); print(x[x.project=='QP-6879'].tail(60)[['record_id','kind','prototype_id','test','value','measured_by','requester','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].to_string(index=False))