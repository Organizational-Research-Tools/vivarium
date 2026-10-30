import pandas as pd
x=pd.read_csv('records.csv');
for p,g in x[x.project=='QP-6879'].groupby('prototype_id'):
 vals=g.groupby(['test','kind']).value.mean().to_dict()
 rec=g.iloc[0];
 print(p, {k:round(v,4) for k,v in vals.items()},'|', [rec[c] for c in ['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']])