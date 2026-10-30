import pandas as pd
x=pd.read_csv('records.csv')
print(x.groupby(['kind','instrument']).size())
# summarize panels per project/proto/instrument
p=x[x.kind=='qualification'].groupby(['project','prototype_id','instrument']).value.agg(['mean','count']).reset_index()
w=p.pivot(index=['project','prototype_id'],columns='instrument',values='mean')
print(w.to_string())
# recipe unique by proto
cols=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
r=x.groupby(['project','prototype_id'])[cols].first()
print('\nRecipes:')
for idx,row in r.iterrows():print(idx, ' '.join(row.astype(str).values))
