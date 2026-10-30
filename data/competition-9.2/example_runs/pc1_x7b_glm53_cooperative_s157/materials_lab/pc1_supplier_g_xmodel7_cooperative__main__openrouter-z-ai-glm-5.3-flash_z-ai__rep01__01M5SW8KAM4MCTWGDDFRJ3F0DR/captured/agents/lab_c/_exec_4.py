import pandas as pd
df=pd.read_csv('records.csv')
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
known=df.dropna(subset=mods)
for t,g in known.groupby('test'):
    print('====',t)
    for m in mods:
        s=g.groupby(m).value.agg(['mean','count']).sort_values('mean',ascending=False)
        print(m); print(s.head(3))
