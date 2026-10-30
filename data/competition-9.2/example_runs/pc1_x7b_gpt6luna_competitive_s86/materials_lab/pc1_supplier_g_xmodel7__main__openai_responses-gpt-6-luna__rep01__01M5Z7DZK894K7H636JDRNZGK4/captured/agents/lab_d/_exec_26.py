import pandas as pd
r=pd.read_csv('records.csv')
print(r.project.value_counts())
print(r.test.unique()); print(r.kind.unique())