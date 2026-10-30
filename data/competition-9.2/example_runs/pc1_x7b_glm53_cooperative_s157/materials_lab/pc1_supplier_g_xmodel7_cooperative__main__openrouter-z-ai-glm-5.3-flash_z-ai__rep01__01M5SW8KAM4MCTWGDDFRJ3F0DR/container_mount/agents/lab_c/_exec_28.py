import pandas as pd
df=pd.read_csv('records.csv')
q=df[df['kind']=='qualification']
for pid in ['p_5XVCC7PF44','p_GM7DHPGB5W']:
    s=q[q['prototype_id']==pid]
    print(pid, s.groupby('test')['value'].agg(['mean','count','min','max']).to_string())
