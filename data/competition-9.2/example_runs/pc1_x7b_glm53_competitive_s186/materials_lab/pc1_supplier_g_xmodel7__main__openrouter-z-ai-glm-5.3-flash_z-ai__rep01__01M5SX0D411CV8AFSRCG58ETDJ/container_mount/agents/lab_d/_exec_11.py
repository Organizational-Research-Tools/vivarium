import pandas as pd
df=pd.read_csv('records.csv')
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
for proj in ['QP-7065','QP-5993','QP-3777','QP-4069']:
    sub=df[df.project==proj]
    agg=sub.groupby(['prototype_id','test'])['value'].mean().unstack()
    print(proj); print(agg.to_string()[:3000])