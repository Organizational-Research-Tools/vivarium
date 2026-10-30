import pandas as pd
df=pd.read_csv('records.csv')
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
print(df[df.prototype_id=='p_MBHXZ56X8R'][mods].drop_duplicates().to_string())
print(df[(df.requester=='lab_e')].groupby(mods)['value'].agg(['mean','count']).sort_values(('value','mean'),ascending=False).head(3).to_string() if 'value' in df else '')