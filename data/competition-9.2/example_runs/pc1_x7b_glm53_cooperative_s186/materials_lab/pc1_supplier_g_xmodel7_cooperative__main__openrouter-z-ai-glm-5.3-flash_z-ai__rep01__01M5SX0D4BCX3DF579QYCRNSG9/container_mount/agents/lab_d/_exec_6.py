import pandas as pd
df = pd.read_csv('records.csv')
q=df[df['project']=='QP-1992']
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
seen=set()
for pid,sub in q.groupby('prototype_id'):
    key=tuple(sub[mods].dropna(axis=1,how='all').iloc[0].dropna())
    quals={t:round(s['value'].mean(),2) for t,s in sub[sub['kind']=='qualification'].groupby('test')}
    exps={t:round(s['value'].mean(),2) for t,s in sub[sub['kind']!='qualification'].groupby('test')}
    print(pid,key,'QUAL:',quals,'EXP:',exps,'n=',len(sub),'meas:',sub['measured_by'].unique())