import pandas as pd
df = pd.read_csv('records.csv')
sub = df[(df.project=='QP-1992')&(df.kind=='qualification')&(df.prototype_id=='p_E16M0W72XW')]
print(sub.groupby(['test','measured_by']).agg(n=('value','size'),mean=('value','mean'),ids=('record_id',lambda s:','.join(s))).to_string())