import pandas as pd
df=pd.read_csv('records.csv')
print(df.shape, df.columns.tolist())
print(df.kind.value_counts())
print(df.groupby(['kind','instrument']).value.agg(['count','mean','min','max']))
# old panels hitting >=78
hi=df[(df.kind!='exploratory')]
print(hi[hi.value>=78].groupby('prototype_id').value.agg(['count','mean']))
