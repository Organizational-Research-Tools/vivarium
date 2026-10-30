import pandas as pd
x=pd.read_csv('records.csv'); y=x[(x.project=='QP-8807')];
cols=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
for pid,g in y.groupby('prototype_id'):
 vals=g.groupby(['test','kind']).value.agg(['count','mean']); rec=g.iloc[0]; comps=','.join(str(rec[c]) for c in cols)
 print(pid,comps, vals.to_dict('index'))