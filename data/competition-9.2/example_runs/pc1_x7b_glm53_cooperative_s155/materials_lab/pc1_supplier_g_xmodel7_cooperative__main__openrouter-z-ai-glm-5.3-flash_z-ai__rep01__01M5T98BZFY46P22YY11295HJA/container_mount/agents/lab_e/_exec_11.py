import pandas as pd
df = pd.read_csv('records.csv')
d = df[df['prototype_id'].isin(['p_C4WKEC66VP','p_7EQCYS545E','p_F08ZZEE267'])]
print(d[['prototype_id','test','kind','value','measured_by']].to_string())
print(d.groupby(['prototype_id','test','kind']).value.agg(['mean','count']))
