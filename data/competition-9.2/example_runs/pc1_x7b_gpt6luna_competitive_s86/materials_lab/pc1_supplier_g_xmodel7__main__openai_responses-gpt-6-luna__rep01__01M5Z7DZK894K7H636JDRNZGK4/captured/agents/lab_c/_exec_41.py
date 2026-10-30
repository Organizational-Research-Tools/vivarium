import pandas as pd
x=pd.read_csv('records.csv')
for p in ['p_K6ZM59ZMJM','p_T2SEB0BAET','p_7CHZ5Y38J7','p_NBE0SSEEDQ','p_SVR5NZMYFM']:
 print(p)
 z=x[x.prototype_id.eq(p)][['project','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].drop_duplicates()
 print(z.to_string(index=False))