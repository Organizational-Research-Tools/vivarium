import pandas as pd
df = pd.read_csv('records.csv')
ids = [p for p in df.prototype_id.unique() if '8QV6JFVW6' in str(p)]
q=df[df.prototype_id.isin(ids)]
for pid,sub in q.groupby('prototype_id'):
    print(pid, sub[['test','kind','value']].groupby(['test','kind']).mean().round(2).to_dict(), 'n', len(sub))
# compositions: shared cols
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
print(q.groupby('prototype_id')[mods].first().dropna(axis=1,how='all').to_string())