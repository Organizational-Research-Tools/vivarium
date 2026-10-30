import pandas as pd
df=pd.read_csv('records.csv')
# what is p_55NSKA6RFT recipe? find its composition in records (registered by lab_b — composition may be known via columns)
g=df[df.prototype_id=='p_55NSKA6RFT']
print(g[['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].dropna().drop_duplicates().to_string())
