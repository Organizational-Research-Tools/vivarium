import pandas as pd
x=pd.read_csv('records.csv'); cols=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
for p in ['p_8M12B6QVE7','p_8M12B6QVE9','p_8M12B6QVED','p_8M12B6QVEB','p_FYYJT2KJ6Z','p_SVR5NZMYFM']:
 print('\n',p); d=x[x.prototype_id==p]; print(d[['kind','instrument','value','measured_by']].to_string(index=False));print(d[cols].drop_duplicates().to_string(index=False))