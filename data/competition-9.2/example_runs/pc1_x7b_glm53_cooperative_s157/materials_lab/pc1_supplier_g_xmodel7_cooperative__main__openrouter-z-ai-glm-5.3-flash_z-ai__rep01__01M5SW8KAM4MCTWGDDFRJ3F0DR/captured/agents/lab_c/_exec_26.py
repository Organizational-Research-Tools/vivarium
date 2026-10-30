import pandas as pd
df=pd.read_csv('records.csv')
q=df[df['kind']=='qualification']
for pid in ['p_YGT9NNJ46M','p_JP4D3NK6YX','p_JP4D3NK6Z8']:
    s=q[q['prototype_id']==pid]
    print(pid, s.groupby('test')['value'].agg(['mean','count','min']).to_string())
