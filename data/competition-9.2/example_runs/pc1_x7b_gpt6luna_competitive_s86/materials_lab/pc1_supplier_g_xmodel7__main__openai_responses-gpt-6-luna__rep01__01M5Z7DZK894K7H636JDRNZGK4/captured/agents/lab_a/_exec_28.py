import pandas as pd
x=pd.read_csv('records.csv'); print(x.kind.value_counts()); print(x.test.value_counts()); print(x[x.instrument=='heat'][['kind','test','value']].head())