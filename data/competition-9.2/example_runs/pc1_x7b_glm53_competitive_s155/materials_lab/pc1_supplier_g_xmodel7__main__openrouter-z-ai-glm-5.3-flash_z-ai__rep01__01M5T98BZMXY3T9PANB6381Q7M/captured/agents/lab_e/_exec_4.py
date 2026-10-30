import pandas as pd
df = pd.read_csv('records.csv')
sub=df[df.prototype_id.isin(['p_9V90B1NZP7','p_9V90B1NZP9','p_AGDEFR9K2N','p_YV3HGJB9MX','p_FFVPVB94W0','p_QYA6J3CEVG','p_BG303V50YP','p_BG303V50YM'])]
print(sub[['prototype_id','instrument','kind','value','measured_by','requester','base_sheet','binder_system','process_profile_2','process_profile_3','conditioning_step','joint_system','surface_treatment','additive_package_1']].drop_duplicates().to_string())
