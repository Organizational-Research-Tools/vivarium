import pandas as pd
x=pd.read_csv('records.csv')
cols=['prototype_id','project','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
for pid in ['p_4AQTFYGQBA','p_H6M64FVH7B','p_W3C23XARDY','p_1R7D8ZYK1G','p_1R7D8ZYK1J','p_1R7D8ZYK1M']:
 d=x[x.prototype_id.eq(pid)]
 print('\n',pid)
 print(d[cols].drop_duplicates().to_string(index=False))
 print(d.groupby(['test','kind','measured_by']).value.agg(['mean','count']).to_string())