import pandas as pd
x=pd.read_csv('records.csv');mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
k=x.dropna(subset=mods)
for inst in ['heat','strength','water']:
 q=k[k.instrument==inst].groupby(['prototype_id','kind']).value.mean().unstack()
 if 'exploratory' in q and 'qualification' in q:
  print(inst, len(q.dropna()),'corr',q.corr().iloc[0,1], 'deltas', (q.qualification-q.exploratory).describe())
  print(q.dropna().sort_values('qualification').tail(8).round(4).to_string())
