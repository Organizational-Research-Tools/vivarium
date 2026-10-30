x=pd.read_csv('records.csv');
cols=['prototype_id','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
print(x[x.project=='QP-8807'].groupby('prototype_id')[cols[1:]].first().to_string())