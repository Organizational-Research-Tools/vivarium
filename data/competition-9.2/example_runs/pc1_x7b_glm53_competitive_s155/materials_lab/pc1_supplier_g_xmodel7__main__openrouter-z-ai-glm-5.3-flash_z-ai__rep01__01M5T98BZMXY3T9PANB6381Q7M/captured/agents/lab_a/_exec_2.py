import pandas as pd
df = pd.read_csv('records.csv')
me = df[(df.measured_by=='lab_a')&(df.kind=='exploratory')]
g = me.groupby('prototype_id').agg(v=('value','mean'), **{c:(c,'first') for c in ['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']})
g = g.sort_values('v',ascending=False)
print(g.to_string())