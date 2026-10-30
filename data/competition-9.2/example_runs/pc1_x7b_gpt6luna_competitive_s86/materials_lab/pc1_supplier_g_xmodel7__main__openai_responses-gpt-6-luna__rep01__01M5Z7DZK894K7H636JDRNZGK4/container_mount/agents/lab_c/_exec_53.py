import pandas as pd
x=pd.read_csv('records.csv'); q=x[x.project.eq('QP-9219')].dropna(subset=['base_sheet']).drop_duplicates('prototype_id'); mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']; top=[('F8Y','7BD','UX3'),('K3K','P2E','96Y'),('K3K','7BD','96Y'),('EB7','P2E','96Y'),('K3K','XD8','UX3'),('74N','4CW','UX3'),('K3K','7BD','UX3'),('EB7','7BD','96Y')];
# common must match
base=['8GP','RK7','YC8','S7U',None,None,'RZ8','9HJ','3XM',None,'JE5','SU2']
for tri in top:
 b=q[(q.base_sheet=='8GP')&(q.secondary_sheet=='RK7')&(q.binder_system=='YC8')&(q.additive_package_1=='S7U')&(q.process_profile_1=='RZ8')&(q.process_profile_2=='9HJ')&(q.process_profile_3=='3XM')&(q.joint_system=='JE5')&(q.conditioning_step=='SU2')&(q.additive_package_2==tri[0])&(q.additive_package_3==tri[1])&(q.surface_treatment==tri[2])]
 print(tri, b.prototype_id.tolist())
 if not b.empty:
  ids=b.prototype_id.tolist(); d=x[x.prototype_id.isin(ids)&x.kind.eq('exploratory')].pivot_table(index='prototype_id',columns='instrument',values='value',aggfunc='mean'); print(d.to_string())