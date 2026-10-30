import pandas as pd, numpy as np
df=pd.read_csv('records.csv')
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
p=df[df.kind=='qualification'].copy()
# panel means per prototype+test
g=p.groupby(['prototype_id','test','instrument']+mods)['value'].agg(['mean','count']).reset_index()
prot=g.pivot_table(index=['prototype_id']+mods, columns='test', values='mean').reset_index()
print(prot[['prototype_id']+mods+['seal hold temperature','edge crush resistance','wet strength retained']].to_string())
