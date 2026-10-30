import pandas as pd
r=pd.read_csv('records.csv'); print(r[r.prototype_id.str.contains('E50TSAR',na=False)].to_string(index=False))