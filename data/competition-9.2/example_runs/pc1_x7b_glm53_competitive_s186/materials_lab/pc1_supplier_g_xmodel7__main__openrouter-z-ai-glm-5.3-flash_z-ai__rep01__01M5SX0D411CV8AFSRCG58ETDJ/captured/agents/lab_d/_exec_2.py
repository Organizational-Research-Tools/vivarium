import pandas as pd
df=pd.read_csv('records.csv')
print(df.columns.tolist())
d=df[(df.measured_by=='lab_d')&(df.test=='heat')]
mods=["base_sheet","secondary_sheet","binder_system","additive_package_1","additive_package_2","additive_package_3","process_profile_1","process_profile_2","process_profile_3","surface_treatment","joint_system","conditioning_step"]
# match column names
cols=[c for c in df.columns if c not in ('record_id','project_id','prototype_id','test','value','measured_by','kind','reading_type')]
print(cols)
d2=df[df.test=='heat']
for c in [x for x in d2.columns if d2[x].dtype==object and x not in ('record_id','project_id','prototype_id','test','measured_by','kind','value')]:
    g=d2.groupby(c)['value'].agg(['mean','count']).sort_values('mean',ascending=False)
    if len(g)>1: print(c); print(g)