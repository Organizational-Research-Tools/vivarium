import pandas as pd
df=pd.read_csv('records.csv')
pan=df[df.kind=='qualification']
for proj in ['QP-1454','QP-1466','QP-6489','QP-2342','QP-3589']:
    print('==',proj)
    g=pan[pan.project==proj].groupby(['prototype_id','test']).value.agg(['mean','count'])
    # group by recipe columns present
    rec=pan[pan.project==proj].groupby('prototype_id')[['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].first()
    piv=g.reset_index().merge(rec,on='prototype_id',how='left')
    for pid,t in piv[['prototype_id','test']].drop_duplicates().values:
        m=piv[(piv.prototype_id==pid)&(piv.test==t)].mean.iloc[0]
        print(pid,t,round(m,3), rec.loc[pid].tolist() if pid in rec.index else '')
