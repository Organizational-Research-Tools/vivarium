import pandas as pd
x=pd.read_csv('records.csv'); x=x[x.kind=='qualification']
g=x.groupby(['project','prototype_id','test']).value.mean().unstack('test')
r=x.groupby(['project','prototype_id']).first()[['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']]
m=r.join(g)
for p in ['QP-9259','QP-5174','QP-9980','QP-6879','QP-9273','QP-3617','QP-7092','QP-9219']:
 d=m.loc[p] if p in m.index.get_level_values(0) else None
 if d is None:continue
 d=d.dropna(subset=['seal hold temperature','edge crush resistance','wet strength retained']).copy()
 if len(d)==0: continue
 d['Hmargin']=(d['seal hold temperature']-78.625)/.25; d['Smargin']=(d['edge crush resistance']-7.235)/.03; d['Wmargin']=(d['wet strength retained']-79.8)/.4
 d['weak']=d[['Hmargin','Smargin','Wmargin']].min(axis=1)
 print('\n'+p,len(d))
 print(d[['seal hold temperature','edge crush resistance','wet strength retained','Hmargin','Smargin','Wmargin','weak']].sort_values('weak',ascending=False).to_string())