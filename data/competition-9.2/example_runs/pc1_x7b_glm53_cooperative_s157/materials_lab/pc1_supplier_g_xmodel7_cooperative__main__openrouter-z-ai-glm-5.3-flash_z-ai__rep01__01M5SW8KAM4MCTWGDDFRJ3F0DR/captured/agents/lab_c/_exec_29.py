import pandas as pd
df=pd.read_csv('records.csv')
q=df[df['kind']=='qualification']
for pid in ['p_GM7DHPGB5W','p_P2FZ2H2S5Z','p_P2FZ2H2S6A']:
    s=q[q['prototype_id']==pid]
    print(pid)
    print(s[['record_id','project','test','value','measured_by']].to_string())
