import pandas as pd
x=pd.read_csv('records.csv'); y=x[x.project.eq('QP-6879')]
print(y.groupby(['prototype_id','instrument']).size().to_string())
print(y.groupby('prototype_id').agg({c:'first' for c in ['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']}).to_string())