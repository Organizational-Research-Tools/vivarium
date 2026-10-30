import pandas as pd
x=pd.read_csv('records.csv'); cols=['prototype_id','base_sheet','joint_system','process_profile_1','additive_package_1','binder_system','process_profile_3','additive_package_2','additive_package_3','surface_treatment']
print(x[x.project=='QP-3617'][cols].drop_duplicates().to_string(index=False))