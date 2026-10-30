import pandas as pd
df=pd.read_csv('records.csv')
df=df[df.kind=='exploratory']
w=df[df.property=='water'].groupby(['project','prototype_id']).reading.agg(['mean','count'])
w=w[w['count']>=2].sort_values('mean',ascending=False).head(20)
print(w)