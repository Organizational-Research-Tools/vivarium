import pandas as pd
r=pd.read_csv('records.csv')
for p in ['p_6H6CV4DA3D','p_6H6CV4DA3F','p_QDC2E5V240','p_7FT9YYT843']:
 x=r[r.prototype_id==p]
 print('\n',p, x[['project','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].drop_duplicates().to_string(index=False))