import pandas as pd, numpy as np
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.metrics import mean_absolute_error, mean_squared_error
x=pd.read_csv('records.csv'); mods=list(x.columns[11:])
ints=[['surface_treatment','process_profile_1','binder_system'],['additive_package_1','binder_system','joint_system'],['binder_system','base_sheet','conditioning_step'],['additive_package_2','additive_package_3','surface_treatment'],['base_sheet','joint_system','process_profile_3'],['binder_system','process_profile_2','conditioning_step'],['base_sheet','joint_system','process_profile_1'],['process_profile_1','additive_package_1','process_profile_3'],['additive_package_3','process_profile_2','additive_package_1'],['process_profile_1','additive_package_3','joint_system'],['process_profile_1','secondary_sheet','additive_package_2'],['secondary_sheet','process_profile_3','additive_package_2']]
# panel means, and add grouped interaction categorical features
pan=x[x.kind=='qualification'].groupby(['project','prototype_id','test']+mods, dropna=False).value.mean().reset_index()
print('panels',len(pan),'tests',pan.test.value_counts().to_dict(),'projects',pan.project.value_counts().to_dict())
for it in ints:
    pan['INT_'+'_'.join(it)] = pan[it].astype(str).agg('|'.join,axis=1)
features=['project']+mods+['INT_'+'_'.join(it) for it in ints]
# one-hot and ridge, LOPO validate
for test in pan.test.unique():
 d=pan[pan.test==test].reset_index(drop=True)
 o=OneHotEncoder(handle_unknown='ignore')
 for a in [0.1,1,10,100]:
  model=make_pipeline(o,Ridge(alpha=a))
  pred=cross_val_predict(model,d[features],d.value,groups=d.project,cv=GroupKFold(n_splits=min(6,d.project.nunique())))
  print(test,a,round(mean_absolute_error(d.value,pred),3),round(np.sqrt(mean_squared_error(d.value,pred)),3), 'range',round(d.value.min(),2),round(d.value.max(),2))
