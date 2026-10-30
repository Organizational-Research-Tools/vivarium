import pandas as pd
df = pd.read_csv('records.csv')
# GQ = QA38AA69GQ composition? check any QP-5653 recent prototypes
d = df[df.prototype_id.str.contains('QA38AA')]
print(d[['prototype_id','test','kind','value']].to_string())
print(d.groupby('prototype_id')[['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].first().to_string())
# XS595HTDBV composition known?
x = df[df.prototype_id=='XS595HTDBV']
print(x.groupby('prototype_id')[['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].first().to_string())