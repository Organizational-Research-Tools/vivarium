import pandas as pd
df = pd.read_csv('records.csv')
m = df[df.prototype_id=='p_E05X2XJNTY']
mods = ['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
print(m[mods].dropna().drop_duplicates().to_string())
print(m[['record_id','project','test','value','measured_by']].head(20).to_string())