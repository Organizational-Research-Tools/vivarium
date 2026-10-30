import pandas as pd
x=pd.read_csv('records.csv'); ids=['p_HNZGFD3XEX','p_04KPN99VK0','p_4J2PHZ8BF9'];
print(x[x.prototype_id.isin(ids)].groupby(['prototype_id','test','kind','measured_by']).value.agg(['count','mean']).to_string())
for i in ids:
 g=x[x.prototype_id==i]; print(i,g.iloc[0][['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].tolist() if len(g) else None)
