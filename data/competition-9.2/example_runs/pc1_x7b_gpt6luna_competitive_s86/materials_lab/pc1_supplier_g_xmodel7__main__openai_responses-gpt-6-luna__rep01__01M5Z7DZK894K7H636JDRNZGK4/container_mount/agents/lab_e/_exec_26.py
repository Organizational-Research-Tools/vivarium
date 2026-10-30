import pandas as pd
x=pd.read_csv('records.csv')
print(x.columns.tolist())
print(x[(x.project=='QP-3617') & (x.prototype_id.str.contains('CD8N',na=False))][['prototype_id','kind','instrument','value','measured_by','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].drop_duplicates().to_string(index=False))
