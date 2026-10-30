import pandas as pd
df = pd.read_csv('records.csv')
for pid in ['p_9JS2853ERS','p_S198NTZJM0','p_0GWK3AF8SQ']:
    sub = df[df.prototype_id==pid]
    print(pid, sub.project.unique(), sub.test.unique(), sub[['test','value']].groupby('test').mean().to_dict())
    print(sub.drop_duplicates('prototype_id')[['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].to_string(index=False))