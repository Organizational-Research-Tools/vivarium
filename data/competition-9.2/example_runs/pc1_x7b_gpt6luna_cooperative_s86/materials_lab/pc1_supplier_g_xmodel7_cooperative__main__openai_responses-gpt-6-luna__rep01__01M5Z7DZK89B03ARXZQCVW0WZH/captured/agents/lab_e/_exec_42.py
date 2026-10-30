import pandas as pd
x=pd.read_csv('records.csv')
print(x.columns.tolist())
print(x.query("project=='QP-9259'").columns.tolist())
print(x.query("project=='QP-9259'").drop_duplicates('prototype_id')[['prototype_id']+[c for c in x.columns if c in ['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']]].to_string(index=False))