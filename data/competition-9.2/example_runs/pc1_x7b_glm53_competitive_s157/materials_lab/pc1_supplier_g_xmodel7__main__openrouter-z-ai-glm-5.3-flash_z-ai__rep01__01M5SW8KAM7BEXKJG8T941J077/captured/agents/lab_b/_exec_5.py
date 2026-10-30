import pandas as pd
df = pd.read_csv('records.csv')
d = df[(df.project=='QP-2236')&(df.test=='edge crush resistance')]
print(d.groupby(['prototype_id','kind'])['value'].agg(['mean','count']).to_string())
print(df[df.prototype_id.str.contains('WJ8|WHY|WJ0|WJ2')][['prototype_id','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].drop_duplicates().to_string())