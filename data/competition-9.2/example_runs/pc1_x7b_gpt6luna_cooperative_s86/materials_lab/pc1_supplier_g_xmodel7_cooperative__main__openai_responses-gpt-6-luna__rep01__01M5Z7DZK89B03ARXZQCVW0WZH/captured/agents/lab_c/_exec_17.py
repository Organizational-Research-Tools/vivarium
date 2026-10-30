import pandas as pd
r=pd.read_csv('records.csv')
q=r[r.project=='QP-9273']
print(q.groupby('prototype_id').agg(n=('record_id','count'),tests=('test',lambda s:','.join(sorted(set(s)))), rec=('record_id','min'), vals=('value','mean')).to_string())
print(q.drop_duplicates('prototype_id')[['prototype_id','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].to_string(index=False))