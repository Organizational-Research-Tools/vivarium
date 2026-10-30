import pandas as pd
df=pd.read_csv('records.csv')
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
d=df[(df.test=='seal hold temperature')&(df.requester=='lab_d')&(df.project=='QP-4757')].copy()
# variants of the best recipe
best=['L7A','T3M','HD9','G7U','9KR','2CS','V9D','9AH','V7P','83B','A6U','9DA']
def diff(r):
    return [mods[i] for i in range(12) if r[mods[i]]!=best[i]]
d['diffs']=d[mods].apply(lambda r: diff(r), axis=1)
d['n']=d['diffs'].apply(len)
sub=d[d.n<=1]
for c in mods:
    g=d.groupby(c)['value'].agg(['mean','count']).sort_values('mean',ascending=False)
    print(c); print(g)