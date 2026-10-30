import pandas as pd
df = pd.read_csv("records.csv")
s = df[(df.project=="QP-8476")&(df.test=="edge crush resistance")&(df.kind=="exploratory")&(df.measured_by=="lab_e")]
mods = ["base_sheet","secondary_sheet","binder_system","additive_package_1","additive_package_2","additive_package_3","process_profile_1","process_profile_2","process_profile_3","surface_treatment","joint_system","conditioning_step"]
print("rows", len(s))
for m in mods:
    g = s.groupby(m).value.agg(['mean','count']).sort_values('mean',ascending=False)
    print(m, {k:(round(v,3),c) for k,v,c in zip(g.index,g['mean'],g['count'])})