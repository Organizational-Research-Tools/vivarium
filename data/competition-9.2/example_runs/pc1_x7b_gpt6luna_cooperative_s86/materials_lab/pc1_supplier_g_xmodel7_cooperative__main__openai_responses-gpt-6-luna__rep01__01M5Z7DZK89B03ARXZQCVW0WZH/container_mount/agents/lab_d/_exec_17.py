import pandas as pd
x=pd.read_csv('records.csv'); print(x.kind.value_counts()); print(x[x.project=='QP-9273'].to_string(index=False))