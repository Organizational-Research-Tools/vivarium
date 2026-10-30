import pandas as pd
df = pd.read_csv('records.csv')
q = df[df.project=='QP-8476']
cols=['prototype_id','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
# compositions of 9KR family
ids=['p_P9QH0GKV8D','p_0NH0CWS5PH','p_0NH0CWS5PK','p_0NH0CWS5PQ','p_0NH0CWS5PF','p_5G545CE5YJ']
print(q[q.prototype_id.isin(ids)][cols].drop_duplicates().to_string())
# best TN6 heat
h = q[(q.test=='seal hold temperature')&(q.secondary_sheet=='TN6')]
print(h.sort_values('value',ascending=False)[['prototype_id','value']+cols[3:]].drop_duplicates('prototype_id').head(10).to_string())