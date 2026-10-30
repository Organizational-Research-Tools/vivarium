import pandas as pd
df=pd.read_csv('records.csv')
for proj in ['QP-1826','QP-8350','QP-3589','QP-4503']:
    w=df[(df.project==proj)&(df.instrument=='water')]
    print(proj, w.groupby(['prototype_id','requester','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']).value.agg(['mean','count']).sort_values('mean',ascending=False).head(8).to_string(), '\n')