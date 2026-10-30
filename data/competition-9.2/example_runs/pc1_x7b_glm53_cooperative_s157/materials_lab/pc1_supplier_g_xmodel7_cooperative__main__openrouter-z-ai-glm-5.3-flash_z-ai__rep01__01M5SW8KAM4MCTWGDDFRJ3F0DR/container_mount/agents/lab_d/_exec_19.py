import pandas as pd
df=pd.read_csv('records.csv')
q=df[df.kind=='qualification']
p=q[q.prototype_id.str.startswith(('p_GM7DHPGB5W','p_P2FZ2H2S5Z','p_P2FZ2H2S6A'))]
print(p[['record_id','project','prototype_id','test','specimen','value','measured_by']].to_string())
print(df[df.prototype_id=='p_GM7DHPGB5W'][['record_id','kind','test','value','measured_by']].to_string())
