import pandas as pd
x=pd.read_csv('records.csv'); d=x[x.project=='QP-3617']; cols=['prototype_id','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step'];
# display for candidates relevant IDs
for p in ['p_2K7NQTDBCH','p_2K7NQTDBCW','p_31ZWZP4Z8G','p_P616PW6MRQ','p_H6M64FVH6V','p_H6M64FVH7B','p_3TS98N4J3A','p_DEH7S6TG4Y','p_W3C23XARE8','p_W3C23XAREG','p_W3C23XARER']:
 r=d[d.prototype_id==p]
 if len(r): print(p, r[cols[1:]].drop_duplicates().to_dict('records'), r.groupby('test').value.mean().to_dict())
