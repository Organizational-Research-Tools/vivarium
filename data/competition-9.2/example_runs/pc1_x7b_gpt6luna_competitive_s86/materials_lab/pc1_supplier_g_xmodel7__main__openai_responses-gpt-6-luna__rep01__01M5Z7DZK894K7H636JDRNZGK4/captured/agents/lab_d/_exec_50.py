import pandas as pd
x=pd.read_csv('records.csv');
for p in ['p_2K7NQTDBCH','p_2K7NQTDBCW','p_1R7D8ZYK1G','p_1R7D8ZYK1J','p_1R7D8ZYK1M','p_3TS98N4J3A','p_H6M64FVH6V','p_H6M64FVH7B']:
 y=x[x.prototype_id==p]; print('\n',p); print(y.groupby(['kind','test']).value.agg(['count','mean'])); print(y.iloc[0][['project','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].to_dict())