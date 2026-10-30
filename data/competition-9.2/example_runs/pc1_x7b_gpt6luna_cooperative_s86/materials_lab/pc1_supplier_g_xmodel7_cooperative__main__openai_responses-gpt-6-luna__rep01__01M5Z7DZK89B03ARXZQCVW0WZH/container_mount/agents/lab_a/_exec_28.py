import pandas as pd
x=pd.read_csv('records.csv')
print(x['project'].value_counts())
y=x[x.project=='QP-6879']
print(y.groupby(['prototype_id','test','measured_by']).value.agg(['count','mean']).round(5).to_string())
print(y[['prototype_id','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].drop_duplicates().to_string(index=False))