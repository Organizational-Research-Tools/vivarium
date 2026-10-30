import pandas as pd
x=pd.read_csv('records.csv'); q=x[(x.project=='QP-6879') & (x.kind=='qualification')]
for pid,g in q.groupby('prototype_id'):
  tests=g.groupby('test').value.mean().to_dict()
  comp=g[['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].dropna().drop_duplicates()
  c=comp.iloc[0].tolist() if not comp.empty else []
  if len(tests)<3 or any((t=='strength' and v>=7.18) or (t=='heat' and v>78.15) for t,v in tests.items()): print(pid,tests,c)
