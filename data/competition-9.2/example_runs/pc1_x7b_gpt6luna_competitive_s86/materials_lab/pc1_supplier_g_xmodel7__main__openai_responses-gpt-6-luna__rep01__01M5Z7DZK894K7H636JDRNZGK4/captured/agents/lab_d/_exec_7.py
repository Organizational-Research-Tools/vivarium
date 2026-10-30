import pandas as pd
x=pd.read_csv('records.csv')
y=x[(x.project=='QP-9219')&(x.instrument=='heat')&(x.kind=='qualification')&(x.prototype_id.str.startswith('p_YBRQHA8K'))]
print(y.groupby(['prototype_id','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step'],dropna=False).agg(n=('value','size'),mean=('value','mean'),minid=('record_id','min'),maxid=('record_id','max')).reset_index().to_string(index=False))