import pandas as pd
x=pd.read_csv('records.csv')
for p in ['p_KBABVTJCX0','p_W33J996BS8','p_FNQB6CMZKJ','p_4BZKCSF0KV','p_0TQMVB0YHY','p_QDC2E5V240','p_NQX11P94JT','p_NQX11P94JW','p_NQX11P94JY']:
 g=x[x.prototype_id==p]
 if len(g):
  print('\n',p, 'recipe',list(g.iloc[0][['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']]))
  print(g.groupby('test').value.mean().to_dict())