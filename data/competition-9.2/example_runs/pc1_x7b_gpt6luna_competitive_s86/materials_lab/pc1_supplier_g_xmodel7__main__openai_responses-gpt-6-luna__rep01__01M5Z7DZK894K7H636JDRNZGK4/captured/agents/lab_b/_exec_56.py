import pandas as pd
x=pd.read_csv('records.csv')
# means per proto/test and pivot
m=x[x.kind=='exploratory'].groupby(['project','prototype_id','test']).value.mean().unstack()
sel=m[(m.get('edge crush resistance')>=7.235)&(m.get('seal hold temperature')>=78.625)&(m.get('wet strength retained')>=79.8)]
print('all exploratory all-pass candidates',sel.to_string())
# strength top, show available tests & recipe
for p in m.sort_values('edge crush resistance',ascending=False).head(20).index.get_level_values(1):
 g=x[x.prototype_id==p]
 print('\n',p,g.project.iloc[0]); print(g.groupby(['test','kind']).value.agg(['mean','count']).to_string())
 print(g.iloc[0][['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].to_dict())
