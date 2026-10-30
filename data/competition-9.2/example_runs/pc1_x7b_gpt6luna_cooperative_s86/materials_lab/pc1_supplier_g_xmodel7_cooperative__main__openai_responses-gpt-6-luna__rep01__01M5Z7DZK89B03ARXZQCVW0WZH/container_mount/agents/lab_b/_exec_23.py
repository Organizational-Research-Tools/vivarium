import pandas as pd
x=pd.read_csv('records.csv'); print(x.columns.tolist()); print(x.shape); print(x.iloc[:3].to_string())