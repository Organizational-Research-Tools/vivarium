import pandas as pd
r=pd.read_csv('records.csv')
# recently measured prototypes in this project
x=r[r.project.eq('QP-3617')]
for p,g in x.groupby('prototype_id'):
    if p.startswith(('p_6H','p_ZV','p_PKA','p_4YH')):
      vals=g.groupby(['test','kind']).value.mean().round(4).to_dict()
      print(p, vals, g[['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].drop_duplicates().iloc[0].to_list())