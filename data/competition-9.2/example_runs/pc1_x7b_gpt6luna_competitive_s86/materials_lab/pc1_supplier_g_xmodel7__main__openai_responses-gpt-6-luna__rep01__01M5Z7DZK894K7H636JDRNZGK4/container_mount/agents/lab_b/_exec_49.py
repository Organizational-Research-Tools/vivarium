import pandas as pd
x=pd.read_csv('records.csv'); q=x[(x.project=='QP-3617') & (x.prototype_id.isin(['p_3TS98N4J3A','p_2K7NQTDBCW','p_8E0645AKSJ','p_1R7D8ZYK1G','p_1R7D8ZYK1M','p_4AQTFYGQBA']))]
cols=['prototype_id','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step','test','kind','value','measured_by']
print(q[cols].drop_duplicates().to_string(index=False))