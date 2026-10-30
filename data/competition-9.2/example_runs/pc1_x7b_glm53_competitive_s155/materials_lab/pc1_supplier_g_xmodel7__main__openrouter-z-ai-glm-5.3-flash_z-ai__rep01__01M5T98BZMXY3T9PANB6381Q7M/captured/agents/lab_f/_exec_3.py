import pandas as pd
df=pd.read_csv('records.csv')
for pid in ['p_YZPT94HHAS','p_0A7VBS65GB','p_DXWB7AN3ZX','p_5J4R9PGAKV']:
    sub=df[df.prototype_id==pid]
    print(pid, sub.project.unique(), sorted(sub.test.unique()))
    print(sub.groupby(['instrument','test']).agg(n=('value','size'),mean=('value','mean')).to_string())
    print(sub[['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].dropna(how='all').head(1).to_string())
    print('measured_by:', sub.measured_by.unique(), 'requester:', sub.requester.unique())
    print()