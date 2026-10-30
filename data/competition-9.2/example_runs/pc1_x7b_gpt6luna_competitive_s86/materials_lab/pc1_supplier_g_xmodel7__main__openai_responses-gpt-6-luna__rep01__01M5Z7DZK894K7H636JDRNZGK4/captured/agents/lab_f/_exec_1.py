import pandas as pd, os
p='records.csv'
print(os.path.exists(p))
if os.path.exists(p):
 d=pd.read_csv(p); print(d.shape); print(d.head().to_string())