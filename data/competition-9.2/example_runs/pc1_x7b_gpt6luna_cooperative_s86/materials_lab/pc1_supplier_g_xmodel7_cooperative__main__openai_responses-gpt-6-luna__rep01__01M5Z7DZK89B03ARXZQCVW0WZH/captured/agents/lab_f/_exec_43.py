import pandas as pd
x=pd.read_csv('records.csv'); q=x[x.project=='QP-9259']; print(q.shape); cols=['prototype_id','test','measured_by','value']
print(q.groupby(['prototype_id','test']).value.agg(['mean','count']).to_string())
print(q.drop_duplicates('prototype_id').set_index('prototype_id')[['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].to_string())