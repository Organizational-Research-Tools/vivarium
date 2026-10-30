import pandas as pd
df=pd.read_csv('records.csv')
print(df[df.record_id.str.startswith('r_DHYF')][['record_id','instrument','test','value','measured_by']])
print(df[(df.project=='QP-5653')&(df.kind=='qualification')][['record_id','test','measured_by','value']])
