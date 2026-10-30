import pandas as pd
d = pd.read_csv('records.csv')
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
q=d[d.project=='QP-1992']
print(q.drop_duplicates('prototype_id')[mods+['prototype_id']].to_string())
print()
print(q[q.prototype_id=='p_Y5EPMGMRXE'][['test','value']].groupby('test').agg(['mean','count']))
