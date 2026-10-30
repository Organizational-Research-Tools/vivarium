import pandas as pd
D=pd.read_csv('records.csv'); mods=[c for c in D if c in ['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']]
w=D.pivot_table(index=['project','prototype_id']+mods,columns='instrument',values='value',aggfunc='mean').reset_index()
print(w[['project','prototype_id','base_sheet','heat','strength','water']].to_string(index=False))
print('unique projects',D.project.unique())