import pandas as pd
x=pd.read_csv('records.csv'); mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']; d=x.dropna(subset=mods).copy();
# group project+recipe+test, identify panel mean pass strength/water; heat either panel/explorer candidates
for (pr,*recipe),g in d.groupby(['project']+mods):
 vals={}
 for test,h in g.groupby('test'):
  vals[test]=(h.kind.iloc[0],len(h),h.value.mean())
 if recipe[0]=='H8Z': continue
 if all(t in vals and vals[t][0]=='qualification' and vals[t][1]>=6 and vals[t][2]>=th for t,th in [('edge crush resistance',7.235),('wet strength retained',79.8)]):
  print(pr, recipe, vals.get('seal hold temperature'))
