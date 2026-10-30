import pandas as pd
D=pd.read_csv('records.csv'); print(D.shape); print(D.columns.tolist()); print(D[D['prototype_id'].astype(str).str.startswith('p_VN7')].to_string(index=False))