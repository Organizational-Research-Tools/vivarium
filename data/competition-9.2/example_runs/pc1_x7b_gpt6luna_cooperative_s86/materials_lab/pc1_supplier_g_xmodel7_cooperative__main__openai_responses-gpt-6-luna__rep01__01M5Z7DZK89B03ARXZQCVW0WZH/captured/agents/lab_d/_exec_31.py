import pandas as pd
r=pd.read_csv('records.csv')
print(r.shape)
# aggregates by prototype/project and test
piv=r.groupby(['project','prototype_id','test']).value.mean().unstack()
print(piv[piv.index.get_level_values(0).isin(['QP-9980','QP-6879'])].to_string())
# all recipes with closest to thresholds per project
print('\nQP9980 records/protos')
print(r[r.project=='QP-9980'].groupby(['prototype_id','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step','test']).value.mean().unstack().to_string())