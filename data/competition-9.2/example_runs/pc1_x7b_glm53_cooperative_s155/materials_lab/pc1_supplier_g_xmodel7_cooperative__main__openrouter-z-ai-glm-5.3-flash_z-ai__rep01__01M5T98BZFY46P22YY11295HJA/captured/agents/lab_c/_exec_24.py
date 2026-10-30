import pandas as pd
df=pd.read_csv('records.csv')
for p in ['p_PSG59ZNNC0','p_WDXM16QHCD','p_2XSDC22S4J','p_QDP2930TBG']:
    d=df[df.prototype_id==p]
    print(p, d[['project','test','value','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].to_string(), '\n')