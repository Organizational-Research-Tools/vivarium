import pandas as pd
df=pd.read_csv('records.csv')
q=df[(df['kind']=='qualification')&(df['prototype_id'].str.startswith('p_GM7DHPGB5'))]
print(q[['record_id','project','prototype_id','test','value','measured_by']].to_string())
# all protos p_GM7DHPG*
print(sorted(set(df['prototype_id'][df['prototype_id'].str.startswith('p_GM7DHPG')])))
# all QP-1586 qualification water/strength receipts
s=df[(df['kind']=='qualification')&(df['project']=='QP-1586')]
print(s[['record_id','prototype_id','test','value','measured_by']].to_string())
