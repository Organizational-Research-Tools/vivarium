import pandas as pd
x=pd.read_csv('records.csv')
cols=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
# only QP3617/6879, qualification heat
q=x[(x.kind=='qualification')&(x.test.str.startswith('seal'))]
means=q.groupby(['project','prototype_id']+cols,dropna=False).value.mean().reset_index()
key=cols.copy(); key.remove('process_profile_2')
for _,r in means.iterrows():
    if r['base_sheet']=='8GP' and r['secondary_sheet']=='RK7' and r['binder_system']=='VQ6' and r['additive_package_1']=='7TW' and r['additive_package_2']=='K3K' and r['additive_package_3']=='XD8' and r['process_profile_1']=='2A4' and r['process_profile_3']=='FJ2' and r['surface_treatment']=='UX3' and r['joint_system']=='YX4' and r['conditioning_step']=='SU2':
        print(r['project'],r['prototype_id'],r['process_profile_2'],r.value)
print('---all exact p2-match groups with 2+')
for k,g in means.groupby(['project']+key):
 if len(g)>1 and k[1]=='8GP' and k[2]=='RK7' and k[3]=='VQ6' and k[4]=='7TW' and k[5]=='K3K' and k[6]=='XD8' and k[7]=='2A4' and k[8]=='FJ2' and k[9]=='UX3' and k[10]=='YX4' and k[11]=='SU2':
  print(k,g[['prototype_id','process_profile_2','value']].to_string(index=False))