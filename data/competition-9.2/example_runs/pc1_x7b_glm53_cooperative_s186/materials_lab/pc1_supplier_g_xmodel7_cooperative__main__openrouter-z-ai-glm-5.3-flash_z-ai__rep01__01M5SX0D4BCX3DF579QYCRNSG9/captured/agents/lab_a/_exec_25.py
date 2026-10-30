import pandas as pd
d=pd.read_csv('records.csv')
def rec(p):
    r=d[d.prototype_id==p]
    cols=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
    return r.iloc[0][cols].tolist() if len(r) else None
for p in ['p_2MJ543QS8W','p_1Z1DHPD5WS','p_V3YHHTAXJX','p_41VPVR8BED']:
    print(p, rec(p))
s=d[d.prototype_id.isin(['p_2MJ543QS8W','p_1Z1DHPD5WS'])]
print(s.groupby(['prototype_id','test','measured_by']).value.agg(['count','mean','min']).round(3))