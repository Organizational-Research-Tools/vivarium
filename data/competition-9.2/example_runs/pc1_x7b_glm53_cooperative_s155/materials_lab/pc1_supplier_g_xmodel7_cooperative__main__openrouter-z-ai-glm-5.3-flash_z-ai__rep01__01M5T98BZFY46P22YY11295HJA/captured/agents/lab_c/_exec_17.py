import pandas as pd
df=pd.read_csv('records.csv')
for p in ['p_C8ZSKAXWWF','p_Q7TGEXGSCT']:
    print(df[df.prototype_id==p].groupby(['test','instrument','measured_by']).value.agg(['mean','count','min','max']).to_string())
# also any other 8WN recipes with water>=78 across projects
w=df[(df.test=='water')&(df.process_profile_2=='8WN')]
g=w.groupby(['prototype_id','project','requester','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']).value.agg(['mean','count'])
print(g[g['mean']>=77.5].to_string())