import pandas as pd
df = pd.read_csv('records.csv')
d = df[df.prototype_id.isin(['p_HQZBRP1VT3','p_HQZBRP1VT7','p_HQZBRP1VT9','p_HQZBRP1VTB','p_HQZBRP1VT5','p_QA38AA69GQ'])]
comp = ['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
print(d.groupby('prototype_id')[comp].first().to_string())
print(d.groupby(['prototype_id','test'])['value'].agg(['mean','count']).to_string())