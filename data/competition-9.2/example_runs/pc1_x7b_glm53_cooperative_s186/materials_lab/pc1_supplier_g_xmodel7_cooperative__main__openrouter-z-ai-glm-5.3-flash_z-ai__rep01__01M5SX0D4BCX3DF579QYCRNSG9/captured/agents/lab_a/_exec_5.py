import pandas as pd, numpy as np
df=pd.read_csv('records.csv')
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
known=df.dropna(subset=['base_sheet'])
expl=known[known.kind=='exploratory']
# effect of conditioning on heat exploratory
for t in ['seal hold temperature','edge crush resistance','wet strength retained']:
    sub=expl[expl.test==t]
    print(t, sub.groupby('conditioning_step')['value'].agg(['mean','count']).round(2).to_dict('index'))
