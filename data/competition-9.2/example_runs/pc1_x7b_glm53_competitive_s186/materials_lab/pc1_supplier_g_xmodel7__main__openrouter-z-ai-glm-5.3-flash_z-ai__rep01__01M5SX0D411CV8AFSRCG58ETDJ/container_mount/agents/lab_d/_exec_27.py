import pandas as pd
df=pd.read_csv('records.csv')
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
# QP-4757 data: heat, water, strength by prototype
q=df[df.project=='QP-4757']
for t in q.test.unique():
    sub=q[q.test==t]
    print(t)
    print(sub.groupby('prototype_id').value.agg(['count','mean']).sort_values('mean',ascending=False).head(8).to_string())
# join comps
kc=df.dropna(subset=mods).groupby('prototype_id')[mods].first()
print(kc.loc[[p for p in q.prototype_id.unique() if p in kc.index]].to_string())