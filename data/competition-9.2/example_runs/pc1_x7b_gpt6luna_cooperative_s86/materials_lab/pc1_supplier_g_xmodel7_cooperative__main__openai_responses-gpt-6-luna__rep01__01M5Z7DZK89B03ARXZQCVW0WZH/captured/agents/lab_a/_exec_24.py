import pandas as pd
x=pd.read_csv('records.csv')
ps=['p_FF5QPYJ1FJ','p_FF5QPYJ1FM','p_FF5QPYJ1FP','p_9YW85TNK93','p_9YW85TNK95']
for p in ps:
 d=x[x.prototype_id==p]
 print('\n',p)
 if len(d):
  print(d[[c for c in ['record_id','kind','test','value','measured_by','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step'] if c in d.columns]].to_string(index=False))