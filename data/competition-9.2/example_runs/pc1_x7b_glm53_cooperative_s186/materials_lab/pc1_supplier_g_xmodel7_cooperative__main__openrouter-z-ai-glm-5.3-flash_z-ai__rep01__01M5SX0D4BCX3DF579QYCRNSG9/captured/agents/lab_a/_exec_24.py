import pandas as pd
d=pd.read_csv('records.csv')
# find any QP-1992 (or QP-5993) prototypes with heat exploratory readings from me, print recipes
for proj in ['QP-1992','QP-5993']:
    q=d[(d.project==proj)&(d.test=='seal hold temperature')]
    g=q.groupby(['prototype_id','measured_by']).value.agg(['count','mean']).round(3)
    print(proj); print(g.to_string())
# recipe lookup for interesting ids
def rec(p):
    r=d[d.prototype_id==p]
    cols=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
    return r.iloc[0][cols].tolist() if len(r) else None
for p in ['p_41VPVR8BED','p_C9J7882FRX']:
    print(p, rec(p))