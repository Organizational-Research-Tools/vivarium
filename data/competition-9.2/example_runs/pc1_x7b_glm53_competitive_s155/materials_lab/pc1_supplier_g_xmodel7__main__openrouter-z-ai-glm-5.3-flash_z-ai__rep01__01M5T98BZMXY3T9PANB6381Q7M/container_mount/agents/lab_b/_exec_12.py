import pandas as pd
df = pd.read_csv('records.csv')
for pid in ['p_FVCMZJEWBX','p_77Z8P69629','p_ZJC86DH7B1']:
    sub=df[df.prototype_id==pid]
    print(pid, sub[['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].dropna(how='all').head(1).to_dict('records'))
    print(sub.groupby('test').agg(n=('value','size'),mn=('value','mean'),mx=('value','max')).to_string())