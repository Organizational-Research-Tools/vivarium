import pandas as pd
r=pd.read_csv('records.csv')
ids=['p_NQYNDKZ3C8','p_NQYNDKZ3CA','p_NQYNDKZ3CG','p_NQYNDKZ3CJ']
s=r[r.prototype_id.isin(ids)]
print(s.groupby(['prototype_id','instrument','test']).value.agg(['mean','count']).to_string())
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
print(s.drop_duplicates('prototype_id')[['prototype_id','project']+mods].to_string(index=False))