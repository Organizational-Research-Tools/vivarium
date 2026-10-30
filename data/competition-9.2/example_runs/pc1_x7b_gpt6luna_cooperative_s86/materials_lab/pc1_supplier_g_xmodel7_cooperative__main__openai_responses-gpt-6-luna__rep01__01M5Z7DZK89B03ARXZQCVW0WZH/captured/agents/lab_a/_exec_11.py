import pandas as pd, numpy as np, itertools
from sklearn.preprocessing import OneHotEncoder
from sklearn.linear_model import Ridge
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import make_pipeline
from sklearn.metrics import mean_absolute_error
x=pd.read_csv('records.csv')
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
# all heat means with compositions known
h=x[(x.test=='seal hold temperature') & x.base_sheet.notna()].groupby(['project','prototype_id']+mods).value.mean().reset_index()
# interaction heat groups
ints=[['surface_treatment','process_profile_1','binder_system'],['additive_package_2','additive_package_3','surface_treatment'],['base_sheet','joint_system','process_profile_3'],['process_profile_1','additive_package_1','process_profile_3'],['additive_package_3','process_profile_2','additive_package_1'],['secondary_sheet','process_profile_3','additive_package_2']]
def fe(df):
 z=pd.DataFrame(index=df.index)
 z['project']=df.project
 for m in mods: z[m]=df[m]
 for j,g in enumerate(ints): z['I'+str(j)]=df[g].astype(str).agg('|'.join,axis=1)
 return z
enc=OneHotEncoder(handle_unknown='ignore')
for a in [0.1,1,10,30,100]:
 model=make_pipeline(OneHotEncoder(handle_unknown='ignore'),Ridge(alpha=a))
 model.fit(fe(h),h.value)
 # train predictions baseline adjustment on q5174 known
 y=h[h.project=='QP-5174'];
 print('alpha',a,'n',len(h),'MAE all',mean_absolute_error(h.value,model.predict(fe(h))))
 print('q5174:')
 for _,r in y.iterrows():
  pred=model.predict(fe(pd.DataFrame([r])))[0]
  print(r.prototype_id, r.value, pred, 'adjust',r.value-pred)
 # held-out recipe MAE grouped project approx
 preds=[]
 for i in range(len(h)):
  tr=h.drop(index=i); te=h.iloc[[i]]
  mod=make_pipeline(OneHotEncoder(handle_unknown='ignore'),Ridge(alpha=a)).fit(fe(tr),tr.value)
  preds.append(mod.predict(fe(te))[0])
 print('LOO MAE',mean_absolute_error(h.value,preds))
# generate 100k random compositions based observed levels
