import pandas as pd
df=pd.read_csv('records.csv')
# water on QP-5653 and QP-6820 recipes: which recipes exist with panels
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
known=df.dropna(subset=mods)
for proj in ['QP-5653','QP-6820','QP-5066','QP-2347','QP-2236','QP-3068']:
    g=known[known.project==proj]
    if len(g)==0: continue
    print('====',proj)
    for t,gt in g.groupby('test'):
        print(gt.value.agg(['mean','count']).round(2).to_dict())
    rec=g[g.kind=='qualification'].groupby('test').value.mean()
    print(rec.round(2))
