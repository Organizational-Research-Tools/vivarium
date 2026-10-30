import pandas as pd
df=pd.read_csv('records.csv')
print(df.columns.tolist())
e=df[df.kind=='exploratory']
w=e[e.test=='water'] if 'test' in e.columns else e
print(df.columns)