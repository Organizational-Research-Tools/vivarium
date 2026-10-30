import pandas as pd
D=pd.read_csv('records.csv'); print(D.test.unique()); print(D.kind.value_counts()); print(D.groupby(['project','prototype_id','test']).value.mean().unstack().to_string())