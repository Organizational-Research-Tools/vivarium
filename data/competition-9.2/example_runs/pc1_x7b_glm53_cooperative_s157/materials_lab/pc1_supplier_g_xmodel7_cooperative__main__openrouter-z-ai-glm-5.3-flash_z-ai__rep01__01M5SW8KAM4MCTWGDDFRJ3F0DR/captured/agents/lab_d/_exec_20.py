import pandas as pd
df=pd.read_csv('records.csv')
q=df[df.kind=='qualification']
# strength panels on PL-80 projects
s=q[(q.test=='edge crush resistance')]
print(s[['record_id','project','prototype_id','value','measured_by']].to_string())
