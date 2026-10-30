import pandas as pd
x=pd.read_csv('records.csv')
print(x.shape)
print(x.groupby(['project','prototype_id','instrument','measured_by']).size().to_string())
# complete panels grouped by project, recipe combination and instrument and means
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
y=x[x.kind=='qualification'].copy()
for keys,g in y.groupby(['project']+mods+['instrument','measured_by']):
 if len(g)>=6:
  print(keys[0],keys[-2],keys[-1], tuple(keys[1:13]),round(g.value.mean(),5))