import pandas as pd
df = pd.read_csv('records.csv')
cols = ['prototype_id','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
print(df[df.prototype_id=='p_KY5FFZSAYN'][cols].drop_duplicates().to_string())
# also lab_a's survivors Y6H, 23Y
ids = df[(df.project=='QP-3589')].prototype_id.unique()
print(ids)
print(df[(df.prototype_id.isin(['p_DSTFRJN4CR']))][cols].drop_duplicates().to_string())