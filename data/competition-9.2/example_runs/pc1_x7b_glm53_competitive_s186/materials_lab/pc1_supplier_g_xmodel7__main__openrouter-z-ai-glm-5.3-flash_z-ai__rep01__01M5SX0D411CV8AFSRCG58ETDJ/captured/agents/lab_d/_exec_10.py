import pandas as pd
df=pd.read_csv('records.csv')
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
d=df[(df.test=='seal hold temperature')&(df.requester=='lab_d')&(df.project=='QP-4757')]
print(d[mods+['value']].sort_values('value',ascending=False).to_string())