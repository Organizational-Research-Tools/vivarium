import pandas as pd
pd.set_option('display.width',250)
df=pd.read_csv('records.csv')
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
h=df[df['test']=='seal hold temperature']
for pid in ['p_5H6XYY0XDG','p_HF7V4XMGSB','p_8XD4XRY0D6','p_2V1CHF70SD','p_QV0MW6RAK0','p_ARD740GBQT','p_XEMGCMK5FP','p_11JRWPJB6H','p_8R4S3DQX4P','p_D78EB69SBD']:
    r=df[df.prototype_id==pid]
    print(pid, round(h[h.prototype_id==pid].value.mean(),2), r.project.iloc[0], list(r[mods].iloc[0]))
