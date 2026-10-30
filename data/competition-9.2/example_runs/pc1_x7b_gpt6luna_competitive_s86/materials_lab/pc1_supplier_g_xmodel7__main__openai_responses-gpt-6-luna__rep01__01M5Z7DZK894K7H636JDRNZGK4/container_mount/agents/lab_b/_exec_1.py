import pandas as pd, os
x=pd.read_csv('records.csv'); print(x.shape); print(x.head().to_string()); print(x.columns.tolist())