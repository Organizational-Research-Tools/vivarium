import pandas as pd
df = pd.read_csv('records.csv')
for pid in ['p_P2FZ2H2S5Z','p_P2FZ2H2S6A']:
    q = df[df.prototype_id==pid]
    print(pid, q[['project','base_sheet','secondary_sheet','binder_system']].drop_duplicates().to_string())
    print(q[['additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].drop_duplicates().to_string())
h = df[df.prototype_id=='p_GM7DHPGB5W']
print(h[['project','base_sheet','binder_system']].drop_duplicates().to_string())
