import pandas as pd
df = pd.read_csv('records.csv')
h = df[(df['prototype']=='p_MBHXZ56X8R')]
cols=[c for c in df.columns]
print(cols)
print(h[[c for c in ['record_id','test','measured_by','value'] if c in df.columns]])
