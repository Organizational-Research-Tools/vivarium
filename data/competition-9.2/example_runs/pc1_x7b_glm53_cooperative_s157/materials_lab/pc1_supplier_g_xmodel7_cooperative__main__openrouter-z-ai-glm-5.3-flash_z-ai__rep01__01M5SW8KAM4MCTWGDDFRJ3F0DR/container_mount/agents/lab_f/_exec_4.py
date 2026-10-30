pd.set_option('display.width',250); pd.set_option('display.max_columns',30)
import pandas as pd
df=pd.read_csv('records.csv')
q=df[df.kind=='qualification']
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
g=q.groupby(['prototype_id','instrument','test']).value.agg(['count','mean']).reset_index()
full=g[g['count']>=6]
full=full.pivot_table(index='prototype_id',columns='test',values='mean')
rec=q.groupby('prototype_id')[mods].agg(lambda s:s.mode()[0])
m=full.join(rec)
print(m.to_string())
