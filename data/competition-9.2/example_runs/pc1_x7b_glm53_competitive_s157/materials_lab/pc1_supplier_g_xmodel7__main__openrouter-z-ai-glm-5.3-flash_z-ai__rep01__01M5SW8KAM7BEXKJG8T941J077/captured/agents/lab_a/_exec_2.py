import pandas as pd
df=pd.read_csv('records.csv')
print(df['test'].unique())
# heat per prototype
h=df[(df['test'].str.contains('heat'))]
print(h.groupby(['project','prototype_id'])['value'].agg(['mean','count']).sort_values('mean',ascending=False).head(12))