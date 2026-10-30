import pandas as pd
x=pd.read_csv('records.csv'); cols=['prototype_id','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
z=x[x.kind=='qualification'].groupby(['project','prototype_id','test']).value.mean().unstack()
for p in ['QP-6879','QP-3617','QP-9259']:
 print('\n'+p)
 ids=z.loc[p].index
 d=x[x.prototype_id.isin(ids)].drop_duplicates('prototype_id')[cols].set_index('prototype_id')
 t=z.loc[p].join(d)
 print(t.to_string())