import pandas as pd
df = pd.read_csv('records.csv')
mods = ['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
s = df[(df['test']=='strength')&(df['project']=='QP-8476')].dropna(subset=mods)
base = s[(s.base_sheet=='V2W')&(s.secondary_sheet=='2YJ')&(s.binder_system=='PU3')&(s.additive_package_1=='G7U')&(s.additive_package_2=='9KR')&(s.additive_package_3=='Z2E')&(s.process_profile_1=='5JK')&(s.process_profile_2=='2FG')&(s.process_profile_3=='V7P')&(s.surface_treatment=='6XN')&(s.joint_system=='YS6')&(s.conditioning_step=='9DA')]
b = base['value'].mean()
print('base mean', b, len(base))
for m in mods:
    for v in s[m].unique():
        sub = s[s[m]==v]
        mv = sub['value'].mean()
        if mv > b + 0.05:
            print(m, v, round(mv-b,3), len(sub))