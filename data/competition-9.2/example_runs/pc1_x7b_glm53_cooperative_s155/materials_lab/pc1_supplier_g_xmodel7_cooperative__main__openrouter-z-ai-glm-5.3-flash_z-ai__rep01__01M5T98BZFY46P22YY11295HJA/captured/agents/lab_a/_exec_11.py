import pandas as pd
df = pd.read_csv('records.csv')
e = df[df.kind=='exploratory']
g = e.groupby(['project','test']).value.agg(['count','mean','max'])
print(g.to_string())
print()
# top heat expl values with recipes
for t in df.test.unique():
    sub = e[e.test==t].sort_values('value',ascending=False).head(10)
    print('=== ',t)
    cols=['record_id','prototype_id','project','measured_by','value','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
    print(sub[cols].to_string(index=False))