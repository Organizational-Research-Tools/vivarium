import pandas as pd
r=pd.read_csv('records.csv')
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
sub=r[r.project.isin(['QP-3617','QP-6879'])]
means=sub.groupby(['project','prototype_id','test','kind']).value.agg(['mean','count']).reset_index()
for project in ['QP-3617','QP-6879']:
 print('\n',project)
 p=sub[sub.project==project].drop_duplicates('prototype_id').set_index('prototype_id')
 for pid,g in means[means.project==project].groupby('prototype_id'):
  sums=', '.join(f"{row.test[:4]}={row['mean']:.4f}{'*' if row.kind=='qualification' else '~'}" for _,row in g.iterrows())
  recipe=' '.join(str(p.loc[pid,m]) for m in mods)
  print(pid, sums, '|',recipe)
