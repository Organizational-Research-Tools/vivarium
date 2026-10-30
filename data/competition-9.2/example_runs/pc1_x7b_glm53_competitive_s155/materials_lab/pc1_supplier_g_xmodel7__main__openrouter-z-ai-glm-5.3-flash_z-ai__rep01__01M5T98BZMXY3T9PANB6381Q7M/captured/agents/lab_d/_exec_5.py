import pandas as pd
df = pd.read_csv('records.csv')
for p in ['p_FVCMZJEWBX','p_GX1KFQW9VY']:
    sub = df[(df.prototype_id==p)&(df.kind=='qualification')]
    print(p, sub.groupby(['test','measured_by'])['value'].agg(['count','mean']))
cols=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
print(df[df.prototype_id=='p_FVCMZJEWBX'][cols].dropna().drop_duplicates().to_string())
# margins
w=(80.194-78.4)/0.4; s=(7.20452-7.10)/0.03; h=(df[(df.prototype_id=='p_FVCMZJEWBX')&(df.instrument=='heat')&(df.kind=='qualification')].value.mean()-77.35)/0.25
print('margins', h, s, w)