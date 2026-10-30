import pandas as pd, os
p='records.csv'; d=pd.read_csv(p); print(d.shape); print(d.columns.tolist()); print(d.head().to_string(index=False))