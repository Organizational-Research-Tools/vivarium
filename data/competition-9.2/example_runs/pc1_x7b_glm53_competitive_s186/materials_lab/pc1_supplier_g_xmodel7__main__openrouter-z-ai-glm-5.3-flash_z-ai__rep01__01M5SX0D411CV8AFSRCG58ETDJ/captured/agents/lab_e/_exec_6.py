import pandas as pd
df = pd.read_csv('records.csv')
mods = ['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
s = df[(df['test']=='strength')&(df['project']=='QP-8476')].dropna(subset=mods)
bvec = dict(base_sheet='V2W', secondary_sheet='2YJ', binder_system='PU3', additive_package_1='G7U',
            additive_package_2='9KR', additive_package_3='Z2E', process_profile_1='5JK',
            process_profile_2='2FG', process_profile_3='V7P', surface_treatment='6XN',
            joint_system='YS6', conditioning_step='9DA')
base = s[(s[mods] == pd.Series(bvec)).all(axis=1)]
print('base rows', len(base), 'mean', base['value'].mean())
b = base['value'].mean()
for _, row in s.iterrows():
    diffs = [m for m in mods if row[m] != bvec[m]]
    if len(diffs)==1 and not (s.loc[row.name, mods] == pd.Series(bvec)).all():
        pass
# simpler: group by each module variant, compare mean when exactly one module differs from base
import numpy as np
res={}
for _, row in s.iterrows():
    diffs = [m for m in mods if row[m] != bvec[m]]
    if len(diffs)==1:
        key=(diffs[0], row[diffs[0]])
        res.setdefault(key, []).append(row['value']-b)
for k,v in sorted(res.items(), key=lambda x:-np.mean(x[1])):
    print(k, round(np.mean(v),3), len(v))
