import pandas as pd
x=pd.read_csv('records.csv'); y=x[x.project=='QP-8807'];
# prototype-level values per test and include recipes
v=y.groupby(['prototype_id','test','kind']).value.agg(['count','mean']).reset_index(); w=v.pivot(index='prototype_id',columns=['test','kind'],values='mean'); rec=y.drop_duplicates('prototype_id').set_index('prototype_id')
print(w.join(rec[['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']],rsuffix='_r').to_string())