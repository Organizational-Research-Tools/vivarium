import pandas as pd
d=pd.read_csv('records.csv')
s=d[(d.record_id.str.startswith('r_Z91BWA64EZ'))&(d.kind!='exploratory')]
print(s[['record_id','test','value']])
print(s.value.mean())