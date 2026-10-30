import pandas as pd
df = pd.read_csv('records.csv')
d = df[(df.project=='QP-3068')&(df.prototype_id.str.startswith('p_PPNKRW75E'))]
print(d.groupby(['prototype_id','kind','test'])['value'].agg(['mean','count']).to_string())