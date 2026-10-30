import pandas as pd
df = pd.read_csv('records.csv')
for pid in ['p_S81ACG3TB8','p_S81ACG3TBK','p_30J118A5XA']:
    r = df[df.prototype_id==pid]
    print(pid, r[['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].dropna(axis=1).head(1).to_dict('records'), r.kind.unique())
