import pandas as pd
x=pd.read_csv('records.csv'); ids=['p_2K7NQTDBCH','p_2K7NQTDBCW','p_3SZ9SPMFY6']; print(x[x.prototype_id.isin(ids)].to_string(index=False))