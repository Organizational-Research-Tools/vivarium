import pandas as pd
df=pd.read_csv('records.csv')
cols=['prototype_id','test','value','measured_by','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
for p in ["p_B0A2AF9B7E","p_0FBSJM80HT","p_MB5K3M1454"]:
    sub=df[df.prototype_id==p]
    if len(sub): print(p, sub.test.value_counts().to_dict(), {c:sub.iloc[0][c] for c in cols[3:]})
    else: print(p,'no rows')
g=df[df.prototype_id=='p_G8S61Z3JR7']
print(g[['record_id','test','value']].to_string())