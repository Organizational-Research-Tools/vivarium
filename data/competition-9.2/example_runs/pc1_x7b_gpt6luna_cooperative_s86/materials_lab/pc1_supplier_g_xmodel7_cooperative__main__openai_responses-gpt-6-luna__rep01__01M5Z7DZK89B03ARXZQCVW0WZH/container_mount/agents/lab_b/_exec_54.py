import pandas as pd
x=pd.read_csv('records.csv'); x=x[(x.kind=='qualification') & (x.project=='QP-6879')]
recipes=x.groupby('prototype_id')[['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].first()
g=x.groupby(['prototype_id','test']).value.mean().unstack()
print(recipes.join(g).sort_values('seal hold temperature',ascending=False).to_string())