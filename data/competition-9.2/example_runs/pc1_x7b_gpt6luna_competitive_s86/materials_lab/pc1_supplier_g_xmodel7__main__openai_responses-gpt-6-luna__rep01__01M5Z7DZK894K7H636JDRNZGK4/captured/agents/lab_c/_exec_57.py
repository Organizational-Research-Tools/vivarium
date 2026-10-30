import pandas as pd
r=pd.read_csv('records.csv')
for pid in ['p_HNZGFD3XEX','p_62M20S6MVN']:
 x=r[r.prototype_id==pid]
 print(pid, x.drop_duplicates('prototype_id').iloc[0][['project','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].to_dict() if len(x) else 'not in file')
 print(x.groupby(['test','kind']).value.agg(['count','mean']) if len(x) else '')