import pandas as pd
x=pd.read_csv('records.csv'); q=x[x.project=='QP-9980']
cols=['prototype_id','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
print(q.groupby(['prototype_id','test']).value.mean().unstack().round(5).to_string())
