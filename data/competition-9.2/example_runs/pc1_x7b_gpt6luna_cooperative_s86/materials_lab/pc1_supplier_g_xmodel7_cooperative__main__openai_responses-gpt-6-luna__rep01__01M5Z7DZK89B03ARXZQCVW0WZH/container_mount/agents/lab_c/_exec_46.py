import pandas as pd
r=pd.read_csv('records.csv'); q=r[r.kind.eq('qualification')]; mods=[c for c in r.columns if c in ['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']]
for proj in ['QP-3617','QP-9259']:
 print('\n',proj)
 d=q[q.project.eq(proj)].groupby(['prototype_id','test']).value.mean().unstack('test')
 recip=q[q.project.eq(proj)].drop_duplicates('prototype_id').set_index('prototype_id')[mods]
 d=d.join(recip)
 for _,row in d.iterrows():
  print(row.name, [row.get(x) for x in ['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']], [round(row.get(x),4) if pd.notna(row.get(x)) else None for x in ['seal hold temperature','edge crush resistance','wet strength retained']])
