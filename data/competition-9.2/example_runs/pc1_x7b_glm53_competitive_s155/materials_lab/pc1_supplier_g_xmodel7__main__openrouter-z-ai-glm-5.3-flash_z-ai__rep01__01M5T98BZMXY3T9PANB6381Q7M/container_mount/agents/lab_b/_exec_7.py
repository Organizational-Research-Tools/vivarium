import pandas as pd
df = pd.read_csv('records.csv')
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
s = df[df.test=='edge crush resistance'].copy()
s['mods']=s[mods].apply(lambda r:'|'.join('?' if pd.isna(v) else str(v) for v in r),axis=1)
e = s[s.kind=='exploratory']
g = e.groupby('prototype_id').agg(n=('value','size'), mn=('value','mean'), mx=('value','max'), mods=('mods','first'))
print(g.sort_values('mn',ascending=False).head(25).to_string())
p = s[s.kind=='qualification']
print(p.groupby('prototype_id').agg(mn=('value','mean'), n=('value','size'), mods=('mods','first')).sort_values('mn',ascending=False).to_string())