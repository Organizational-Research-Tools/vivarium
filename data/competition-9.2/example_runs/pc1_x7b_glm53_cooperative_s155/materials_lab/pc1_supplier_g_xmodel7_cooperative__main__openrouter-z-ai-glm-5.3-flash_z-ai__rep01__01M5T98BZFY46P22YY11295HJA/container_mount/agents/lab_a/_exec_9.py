import pandas as pd
df=pd.read_csv('records.csv')
for pid in ['p_6SVD7WN5N8','p_T24APMPPAY','p_ZPA7AND7FM']:
    sub=df[(df.prototype_id==pid)]
    print(pid, df[df.prototype_id==pid][['project','kind','test','value']].groupby(['kind','test']).value.agg(['mean','count']))
    print(sub[['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].dropna(axis=1).drop_duplicates().to_string())