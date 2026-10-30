import pandas as pd
x=pd.read_csv('records.csv')
d=x[x.project=='QP-9980'].copy()
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
# map mean by prototype per test
for p,g in d.groupby('prototype_id'):
 means=g.groupby('test').value.mean().to_dict()
 recipe=g[mods].dropna().drop_duplicates()
 if len(recipe):
  print(p,recipe.iloc[0].to_list(),{k:round(v,4) for k,v in means.items()})