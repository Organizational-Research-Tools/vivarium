import pandas as pd, itertools
df = pd.read_csv("records.csv")
s = df[(df.project=="QP-8476")&(df.test=="edge crush resistance")&(df.kind=="exploratory")&(df.measured_by=="lab_e")]
mods = ["secondary_sheet","binder_system","additive_package_1","additive_package_2","additive_package_3","process_profile_2","surface_treatment","joint_system","conditioning_step","base_sheet"]
# pairwise interaction effect vs additive average
for m in mods:
    g = s.groupby(m).value.mean()
    eff = g - s.value.mean()
    top = eff.nlargest(3); bot=eff.nsmallest(2)
    print(m, {k:round(v,3) for k,v in top.items()}, {k:round(v,3) for k,v in bot.items()})
# best two-variant combos
for m1,m2 in itertools.combinations(mods,2):
    g = s.groupby([m1,m2]).value.agg(['mean','count'])
    g=g[g['count']>=2]
    if len(g)>1:
        top=g['mean'].max(); idx=g['mean'].idxmax()
        print(m1,m2,idx,round(top,3))