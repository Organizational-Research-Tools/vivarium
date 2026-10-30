import pandas as pd
df = pd.read_csv('records.csv')
sub=df[df.prototype_id=='p_FVCMZJEWBX']
print(sub.groupby(['test','kind']).agg(n=('value','size'),mn=('value','mean'),by=('measured_by',lambda x:','.join(sorted(set(x))))).to_string())
print(sub[sub.kind=='qualification'].groupby('test').agg(mn=('value','mean'),ids=('record_id',lambda x:','.join(x))).to_string())