import pandas as pd
d=pd.read_csv('records.csv')
ids=['p_P5WACE5V1Z','p_P5WACE5V1X','p_461G82NY1N','p_7PX4NYK5ZZ','p_MT90KYFJVE','p_2Y038RWVAZ']
s=d[d.prototype_id.isin(ids)]
print(s.groupby(['prototype_id','test','measured_by']).value.agg(['count','mean']).round(3))
def rec(p):
    r=d[d.prototype_id==p]
    cols=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
    return r.iloc[0][cols].tolist() if len(r) else None
for p in ids:
    print(p, rec(p))
print('my units ok')