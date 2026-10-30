import pandas as pd
df = pd.read_csv("records.csv")
sub = df[(df.project=="QP-8476")]
print(sub.kind.unique(), sub.test.unique(), len(sub))
s = sub[(sub.test=="strength")]
print(s.groupby(['kind','measured_by']).size())
mods = ["base_sheet","secondary_sheet","binder_system","additive_package_1","additive_package_2","additive_package_3","process_profile_1","process_profile_2","process_profile_3","surface_treatment","joint_system","conditioning_step"]
s2 = s[s.kind=="exploratory"]
print("expl rows:", len(s2))
for m in mods:
    g = s2.groupby(m).value.agg(['mean','count']).sort_values('mean',ascending=False)
    print(m, dict(zip(g.index, zip(g['mean'].round(3), g['count']))))