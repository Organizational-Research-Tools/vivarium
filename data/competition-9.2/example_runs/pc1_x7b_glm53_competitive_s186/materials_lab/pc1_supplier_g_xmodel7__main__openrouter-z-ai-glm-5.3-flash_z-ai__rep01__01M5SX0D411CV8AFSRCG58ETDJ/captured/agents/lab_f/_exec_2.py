import pandas as pd, numpy as np
df = pd.read_csv('records.csv')
w = df[(df.test=='wet strength retained')&(df.kind=='exploratory')].copy()
mods = ['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
for m in mods:
    g = w.groupby([m,'project']).value.agg(['mean','count'])
    print(m); print(g[g['count']>=2].to_string()); print()
