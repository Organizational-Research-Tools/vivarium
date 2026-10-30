import pandas as pd
df = pd.read_csv('records.csv')
cols=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
target = ['73S','9AF','DQ9','V5J','NS4','S3J','3RB','GL8','49R','RQ5','8K5','UZ4']
m = (df[cols]==target).all(axis=1) & df[cols].notna().all(axis=1)
print(df[m][['record_id','kind','test','value','measured_by','prototype_id']].to_string())
# water receipts in QP-1454 above 79.5
q = df[(df.kind=='qualification')&(df.test=='wet strength retained')&(df.value>79.4)]
print(q[['record_id','project','value','prototype_id','measured_by']].to_string())
