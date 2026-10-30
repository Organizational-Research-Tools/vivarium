import pandas as pd
p=pd.read_csv('records.csv')
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
q=p[p.kind.eq('qualification')].groupby(['project','prototype_id','test']).value.mean().unstack('test')
meta=p.groupby('prototype_id').first()[['project']+mods]
q=q.join(meta,how='left')
q['margin']=q.apply(lambda r:min((r.get('seal hold temperature',0)-77.5)/.25,(r.get('edge crush resistance',0)-7.1)/.03,(r.get('wet strength retained',0)-78)/.4),axis=1)
for pr,g in q.groupby('project'):
 print('\n',pr)
 print(g[['seal hold temperature','edge crush resistance','wet strength retained','margin']+mods].to_string(index=False))