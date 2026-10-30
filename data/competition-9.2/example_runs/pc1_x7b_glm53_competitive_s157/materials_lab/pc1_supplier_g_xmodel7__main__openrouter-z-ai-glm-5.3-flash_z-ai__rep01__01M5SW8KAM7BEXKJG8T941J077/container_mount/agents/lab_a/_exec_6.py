import pandas as pd
df=pd.read_csv('records.csv')
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
h=df[df['test']=='seal hold temperature'].copy()
known=h.dropna(subset=['base_sheet'])
print(len(known), known.prototype_id.nunique())
g=known.groupby('prototype_id').agg(mean=('value','mean'), **{m:(m,'first') for m in mods})
g=g.sort_values('mean',ascending=False)
print(g.head(20).to_string())
# also water-passing recipes with their heat
w=df[df['test']=='wet strength retained'].groupby('prototype_id')['value'].mean()
s=df[df['test']=='edge crush resistance'].groupby('prototype_id')['value'].mean()
g2=g.copy(); g2['water']=w; g2['strength']=s
print(g2[(g2.water>77)&(g2.strength>7.1)].sort_values('mean',ascending=False).head(15).to_string())
