import pandas as pd
df=pd.read_csv('records.csv')
k=df.dropna(subset=['base_sheet'])
h=k[(k.project=='QP-8476')&(k.test=='seal hold temperature')]
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
for m in mods:
    g=h.groupby(m)['value'].agg(['mean','count']).round(2)
    print(m); print(g.to_string())
