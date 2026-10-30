import pandas as pd
x=pd.read_csv('records.csv'); x=x[x.project.isin(['QP-3617','QP-6879','QP-9273'])]; mods=[c for c in x.columns if c in ['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']]; y=x[(x.kind=='qualification') & x[mods].notna().all(axis=1)].copy(); y['recipe']=y[mods].astype(str).agg('|'.join,axis=1); g=y.groupby(['project','recipe','test']).agg(n=('value','count'),mean=('value','mean'),ids=('prototype_id',lambda s:','.join(sorted(set(s))))).reset_index();
for (pr,recipe),z in g.groupby(['project','recipe']):
 d={r.test:(r.n,r.mean,r.ids) for r in z.itertuples()}; goodH=('seal hold temperature' in d and d['seal hold temperature'][0]>=6 and d['seal hold temperature'][1]>=78.625); goodS=('edge crush resistance' in d and d['edge crush resistance'][0]>=6 and d['edge crush resistance'][1]>=7.235); goodW=('wet strength retained' in d and d['wet strength retained'][0]>=6 and d['wet strength retained'][1]>=79.8)
 if goodH and goodW: print('H&W',pr,d)
 if goodH and goodS: print('H&S',pr,d)
 if goodS and goodW: print('S&W',pr,d)
